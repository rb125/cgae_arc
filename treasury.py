"""
Treasury — Real USDC wallet on Arc that pays agents for completed tasks.

Treasury address: 0x792CD84f40f16A9C78d2586496ae8937C485e218
Agents get paid on-chain via ERC20 transfer after each task.
"""

import hashlib
import json
import logging
import os
import time
import urllib.request
from dataclasses import dataclass, field
from eth_account import Account
from eth_account.signers.local import LocalAccount

logger = logging.getLogger(__name__)

RPC = os.environ.get("ARC_RPC_URL", "https://rpc.testnet.arc-node.thecanteenapp.com/v1/swrm_76131d80539359c3dd1117cdd75cd15e39aa6bff320e9ac6176103b5fc869f1f")
USDC = os.environ.get("USDC_CONTRACT_ADDRESS", "0x3600000000000000000000000000000000000000")
CHAIN_ID = 5042002

# Payment amounts per task (in USDC)
TASK_PAYMENTS = {
    "regime_detection": 0.01,
    "rebalance": 0.05,
    "yield_optimization": 0.005,
}


def _rpc_call(method: str, params: list) -> dict:
    payload = json.dumps({"jsonrpc": "2.0", "method": method, "params": params, "id": 1}).encode()
    req = urllib.request.Request(RPC, data=payload, headers={"Content-Type": "application/json"})
    resp = urllib.request.urlopen(req, timeout=15)
    return json.loads(resp.read())


def _agent_address(name: str) -> str:
    seed = hashlib.sha256(f"cgae-agent-{name}".encode()).hexdigest()
    return Account.from_key("0x" + seed).address


@dataclass
class PaymentRecord:
    agent: str
    task: str
    amount_usdc: float
    tx_hash: str
    timestamp: float


class Treasury:
    def __init__(self):
        pk = os.environ.get("ARC_PRIVATE_KEY", "")
        if not pk:
            raise EnvironmentError("ARC_PRIVATE_KEY not set")
        self._account: LocalAccount = Account.from_key(pk)
        self.address = self._account.address
        self.payments: list[PaymentRecord] = []
        self.total_paid: float = 0.0
        self._nonce: int | None = None
        self._storage = "/tmp/cgae_payments.json"
        self._load()

    def _load(self):
        try:
            with open(self._storage, "r") as f:
                records = json.load(f)
            self.payments = [PaymentRecord(**r) for r in records]
            self.total_paid = sum(p.amount_usdc for p in self.payments)
            logger.info(f"Loaded {len(self.payments)} payment records from disk")
        except (FileNotFoundError, json.JSONDecodeError):
            pass

    def _save(self):
        try:
            with open(self._storage, "w") as f:
                json.dump([{"agent": p.agent, "task": p.task, "amount_usdc": p.amount_usdc,
                            "tx_hash": p.tx_hash, "timestamp": p.timestamp} for p in self.payments], f)
        except Exception as e:
            logger.error(f"Save failed: {e}")

    def balance(self) -> float:
        """Read real USDC balance from Arc."""
        try:
            call_data = "0x70a08231" + self.address[2:].lower().zfill(64)
            result = _rpc_call("eth_call", [{"to": USDC, "data": call_data}, "latest"])
            raw = result.get("result", "0x0")
            return int(raw, 16) / 1e6
        except Exception as e:
            logger.error(f"Balance read failed: {e}")
            return -1

    def _get_nonce(self) -> int:
        if self._nonce is None:
            result = _rpc_call("eth_getTransactionCount", [self.address, "latest"])
            self._nonce = int(result["result"], 16)
        nonce = self._nonce
        self._nonce += 1
        return nonce

    def pay_agent(self, agent_name: str, task: str) -> PaymentRecord | None:
        """Send real USDC to agent address for a completed task."""
        amount = TASK_PAYMENTS.get(task, 0.01)
        to_address = _agent_address(agent_name)
        amount_atomic = int(amount * 1e6)

        # Check balance
        bal = self.balance()
        if bal < amount:
            logger.warning(f"Treasury low: ${bal:.4f} < ${amount} for {agent_name}/{task}")
            return None

        try:
            # ERC20 transfer(address,uint256)
            transfer_data = (
                "0xa9059cbb"
                + to_address[2:].lower().zfill(64)
                + hex(amount_atomic)[2:].zfill(64)
            )

            nonce = self._get_nonce()

            tx = {
                "to": USDC,
                "data": transfer_data,
                "value": 0,
                "gas": 100000,
                "gasPrice": 1000000000,  # 1 gwei
                "nonce": nonce,
                "chainId": CHAIN_ID,
            }

            signed = self._account.sign_transaction(tx)
            raw_tx = "0x" + signed.raw_transaction.hex()

            result = _rpc_call("eth_sendRawTransaction", [raw_tx])

            if "error" in result:
                logger.error(f"TX failed: {result['error']}")
                # Reset nonce on failure so next attempt re-fetches
                self._nonce = None
                return None

            tx_hash = result.get("result", "")
            record = PaymentRecord(
                agent=agent_name, task=task, amount_usdc=amount,
                tx_hash=tx_hash, timestamp=time.time(),
            )
            self.payments.append(record)
            self.total_paid += amount
            self._save()
            logger.info(f"💸 Paid ${amount} to {agent_name} for {task} | tx: {tx_hash[:18]}...")
            return record

        except Exception as e:
            logger.error(f"Payment failed: {e}")
            return None

    def summary(self) -> dict:
        bal = self.balance()
        return {
            "address": self.address,
            "balance_usdc": bal,
            "total_paid": self.total_paid,
            "payments_count": len(self.payments),
            "recent_payments": [
                {"agent": p.agent, "task": p.task, "amount": p.amount_usdc,
                 "tx_hash": p.tx_hash, "time": p.timestamp}
                for p in self.payments[-20:]
            ],
            "agent_wallets": {
                name: _agent_address(name)
                for name in ["nova-pro", "Kimi-K2.5", "DeepSeek-V3.2", "MiniMax-M2.5"]
            },
        }
