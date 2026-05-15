#!/usr/bin/env python3
"""
On-Chain Setup — Register and certify all CGAE agents on Arc Testnet.

Requires .env with:
  ARC_PRIVATE_KEY, CGAE_CONTRACT_ADDRESS, USDC_CONTRACT_ADDRESS

Usage:
    python scripts/onchain_setup.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=True)

from cgae_engine.gate import GateFunction, RobustnessVector, Tier
from audit_pipeline import AuditPipeline, _to_basis_points

# Agent configs — same as in the portfolio runner
AGENTS = [
    {"name": "nova-pro", "role": "regime_detector", "robustness": RobustnessVector(cc=0.55, er=0.60, as_=0.50, ih=0.85)},
    {"name": "claude-sonnet-4", "role": "rebalancer", "robustness": RobustnessVector(cc=0.82, er=0.78, as_=0.70, ih=0.92)},
    {"name": "nova-lite", "role": "yield_optimizer", "robustness": RobustnessVector(cc=0.52, er=0.55, as_=0.48, ih=0.82)},
    {"name": "adversary", "role": "attacker", "robustness": RobustnessVector(cc=0.35, er=0.40, as_=0.30, ih=0.75)},
]


def main():
    gate = GateFunction()
    pipeline = AuditPipeline()
    pipeline._connect()

    print(f"Admin: {pipeline._account.address}")
    print(f"Contract: {pipeline._contract.address}")
    print(f"Chain ID: {pipeline._w3.eth.chain_id}")
    print()

    # Since we only have one deployer key, we register all agents under the same address.
    # In production, each agent would have its own Circle wallet.
    # For the demo, we register once and certify multiple times to show tier changes.

    # Check if already registered
    agent_data = pipeline._contract.functions.agents(pipeline._account.address).call()
    already_registered = agent_data[0] != "0x0000000000000000000000000000000000000000"

    if not already_registered:
        print("Registering agent on-chain...")
        tx = pipeline.register_agent("cgae-portfolio-manager")
        print(f"  ✅ Registered. tx: {tx}")
    else:
        print("  Agent already registered on-chain.")

    print()

    # Certify with each agent's robustness to demonstrate tier computation
    for agent in AGENTS:
        r = agent["robustness"]
        tier = gate.evaluate(r)
        print(f"Certifying {agent['name']} (T{tier.value})...")
        print(f"  CC={r.cc:.2f} ER={r.er:.2f} AS={r.as_:.2f} IH={r.ih:.2f}")

        from cgae_engine.audit import AuditResult
        result = AuditResult(agent_id=agent["name"], robustness=r)
        tx = pipeline.certify_on_chain(pipeline._account.address, result)
        print(f"  ✅ Certified. tx: {tx}")

        # Read back
        on_chain_tier = pipeline._contract.functions.getAgentTier(pipeline._account.address).call()
        on_chain_budget = pipeline._contract.functions.getAgentBudget(pipeline._account.address).call()
        print(f"  On-chain: T{on_chain_tier}, budget=${on_chain_budget / 1e6}")
        print()

    # Final state
    agent_count = pipeline._contract.functions.getAgentCount().call()
    print(f"Total agents registered: {agent_count}")
    print(f"Explorer: https://testnet.arcscan.app/address/{pipeline._contract.address}")


if __name__ == "__main__":
    main()
