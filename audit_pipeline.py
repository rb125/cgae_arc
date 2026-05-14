"""
Audit Pipeline — Runs CDCT/DDFT/AGT audits and updates on-chain tier certifications.

Flow:
  1. Register agents on CGAE.sol (if not already registered)
  2. Run audit battery via Vercel-hosted framework APIs
  3. Compute robustness vector (weakest-link gate)
  4. Call certifyAgent on-chain with scores
  5. Agents can now trade within their certified tier budget

Requires:
  - Framework APIs running (Vercel or localhost:8001-8003)
  - Arc RPC + deployer private key (for on-chain certification)
  - CGAE contract deployed on Arc
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware

from cgae_engine.gate import GateFunction, RobustnessVector, Tier
from cgae_engine.audit import AuditOrchestrator, AuditResult
from cgae_engine.models_config import CONTESTANT_MODELS

logger = logging.getLogger(__name__)


@dataclass
class OnChainAgent:
    address: str
    model_name: str
    tier: Tier
    robustness: RobustnessVector
    tx_hash: str


def _load_contract_abi() -> list:
    """Load CGAE.sol ABI from Hardhat artifacts."""
    import pathlib
    artifact_path = pathlib.Path(__file__).parent / "artifacts" / "contracts" / "CGAE.sol" / "CGAE.json"
    if not artifact_path.exists():
        raise FileNotFoundError(f"Compile contracts first: npx hardhat compile. Missing: {artifact_path}")
    with open(artifact_path) as f:
        return json.load(f)["abi"]


def get_web3() -> Web3:
    """Connect to Arc RPC."""
    rpc_url = os.environ.get("ARC_RPC_URL", "https://rpc.arc.network")
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    if not w3.is_connected():
        raise ConnectionError(f"Cannot connect to Arc RPC: {rpc_url}")
    return w3


def get_cgae_contract(w3: Web3):
    """Get CGAE contract instance."""
    address = os.environ.get("CGAE_CONTRACT_ADDRESS", "")
    if not address:
        raise EnvironmentError("Set CGAE_CONTRACT_ADDRESS in .env")
    abi = _load_contract_abi()
    return w3.eth.contract(address=Web3.to_checksum_address(address), abi=abi)


def _model_arch_hash(model_name: str) -> bytes:
    """Generate a 16-byte architecture hash from model name."""
    return hashlib.md5(model_name.encode()).digest()


def _to_basis_points(score: float) -> int:
    """Convert [0,1] float to [0,10000] uint16 for on-chain storage."""
    return int(max(0, min(10000, score * 10000)))


class AuditPipeline:
    """
    End-to-end audit pipeline: framework APIs → on-chain certification.
    """

    def __init__(self):
        self.gate = GateFunction()
        self.orchestrator = AuditOrchestrator()
        self._w3: Optional[Web3] = None
        self._contract = None
        self._account = None

    def _connect(self):
        """Lazy connect to Arc."""
        if self._w3 is None:
            self._w3 = get_web3()
            self._contract = get_cgae_contract(self._w3)
            pk = os.environ.get("ARC_PRIVATE_KEY", "")
            if not pk:
                raise EnvironmentError("Set ARC_PRIVATE_KEY in .env")
            self._account = self._w3.eth.account.from_key(pk)
            logger.info(f"Connected to Arc. Admin: {self._account.address}")

    def _send_tx(self, tx_fn):
        """Build, sign, and send a transaction."""
        tx = tx_fn.build_transaction({
            "from": self._account.address,
            "nonce": self._w3.eth.get_transaction_count(self._account.address),
            "gas": 500_000,
            "gasPrice": self._w3.eth.gas_price,
        })
        signed = self._account.sign_transaction(tx)
        tx_hash = self._w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = self._w3.eth.wait_for_transaction_receipt(tx_hash)
        return receipt

    def register_agent(self, model_name: str) -> str:
        """Register an agent on-chain. Returns tx hash."""
        self._connect()
        arch_hash = _model_arch_hash(model_name)
        tx_fn = self._contract.functions.registerAgent(arch_hash, model_name)
        receipt = self._send_tx(tx_fn)
        logger.info(f"Registered {model_name} on-chain. tx={receipt.transactionHash.hex()}")
        return receipt.transactionHash.hex()

    def run_audit(self, model_name: str) -> AuditResult:
        """
        Run the audit battery against a model via framework APIs.
        Uses pre-computed scores from Vercel-hosted CDCT/DDFT/AGT.
        """
        logger.info(f"Auditing {model_name}...")
        result = self.orchestrator.audit_from_results(
            agent_id=model_name,
            model_name=model_name,
        )
        tier = self.gate.evaluate(result.robustness)
        logger.info(
            f"  {model_name}: CC={result.robustness.cc:.3f} ER={result.robustness.er:.3f} "
            f"AS={result.robustness.as_:.3f} IH={result.robustness.ih:.3f} → T{tier.value}"
        )
        return result

    def certify_on_chain(self, agent_address: str, result: AuditResult) -> str:
        """Write audit certification to CGAE.sol."""
        self._connect()
        r = result.robustness
        audit_cid = result.audit_storage_cid or f"local:{result.agent_id}"

        tx_fn = self._contract.functions.certifyAgent(
            Web3.to_checksum_address(agent_address),
            _to_basis_points(r.cc),
            _to_basis_points(r.er),
            _to_basis_points(r.as_),
            _to_basis_points(r.ih),
            audit_cid,
        )
        receipt = self._send_tx(tx_fn)
        logger.info(f"Certified {result.agent_id} on-chain. tx={receipt.transactionHash.hex()}")
        return receipt.transactionHash.hex()

    def run_full_pipeline(self, agent_addresses: dict[str, str]) -> list[OnChainAgent]:
        """
        Full pipeline: audit all models → certify on-chain.

        Args:
            agent_addresses: {model_name: wallet_address} mapping
                             (from Circle wallet creation or manual)
        Returns:
            List of OnChainAgent with tier assignments
        """
        results = []
        for model_name, address in agent_addresses.items():
            # 1. Audit
            audit_result = self.run_audit(model_name)

            # 2. Certify on-chain
            tx_hash = self.certify_on_chain(address, audit_result)

            # 3. Record
            tier = self.gate.evaluate(audit_result.robustness)
            results.append(OnChainAgent(
                address=address,
                model_name=model_name,
                tier=tier,
                robustness=audit_result.robustness,
                tx_hash=tx_hash,
            ))

        return results

    def run_audit_only(self, model_names: Optional[list[str]] = None) -> dict[str, AuditResult]:
        """
        Run audits without on-chain certification (offline mode).
        Useful for testing or when Arc is not available.
        """
        names = model_names or [m["model_name"] for m in CONTESTANT_MODELS]
        results = {}
        for name in names:
            results[name] = self.run_audit(name)
        return results


def main():
    """CLI entry point: run audits and print tier assignments."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    print("=" * 60)
    print("CGAE Audit Pipeline — Arc x Circle")
    print("=" * 60)

    pipeline = AuditPipeline()
    results = pipeline.run_audit_only()

    gate = GateFunction()
    print(f"\n{'Model':<20} {'CC':<6} {'ER':<6} {'AS':<6} {'IH':<6} {'Tier':<5} {'Budget':<10}")
    print("-" * 59)
    for name, result in results.items():
        r = result.robustness
        tier = gate.evaluate(r)
        budget = gate.budget_ceiling(tier)
        print(f"{name:<20} {r.cc:<6.3f} {r.er:<6.3f} {r.as_:<6.3f} {r.ih:<6.3f} T{tier.value:<4} ${budget}")

    print("\nTo certify on-chain, set ARC_RPC_URL, ARC_PRIVATE_KEY, CGAE_CONTRACT_ADDRESS")
    print("and provide agent wallet addresses.")


if __name__ == "__main__":
    main()
