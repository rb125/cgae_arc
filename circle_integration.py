"""
Circle SDK Integration — Wallets, Paymaster, USYC.

Provides:
- Dev-controlled wallets for each trading agent (one wallet per model)
- Paymaster integration (gas fees paid in USDC)
- USYC allocation for idle capital between trades

Requires:
  CIRCLE_API_KEY       — from Circle Developer Console
  CIRCLE_ENTITY_SECRET — registered entity secret for wallet encryption
"""

from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass
from typing import Optional

import requests

logger = logging.getLogger(__name__)

CIRCLE_BASE_URL = "https://api.circle.com/v1/w3s"


@dataclass
class AgentWallet:
    wallet_id: str
    wallet_set_id: str
    address: str
    blockchain: str
    model_name: str


class CircleClient:
    """Circle Developer-Controlled Wallets client for CGAE agents."""

    def __init__(self):
        self.api_key = os.environ.get("CIRCLE_API_KEY", "")
        self.entity_secret = os.environ.get("CIRCLE_ENTITY_SECRET", "")
        if not self.api_key:
            raise EnvironmentError("Missing CIRCLE_API_KEY")
        if not self.entity_secret:
            raise EnvironmentError("Missing CIRCLE_ENTITY_SECRET")

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _post(self, path: str, payload: dict) -> dict:
        url = f"{CIRCLE_BASE_URL}{path}"
        resp = requests.post(url, json=payload, headers=self._headers(), timeout=30)
        resp.raise_for_status()
        return resp.json().get("data", {})

    def _get(self, path: str) -> dict:
        url = f"{CIRCLE_BASE_URL}{path}"
        resp = requests.get(url, headers=self._headers(), timeout=30)
        resp.raise_for_status()
        return resp.json().get("data", {})

    def create_wallet_set(self, name: str) -> str:
        """Create a wallet set. Returns wallet_set_id."""
        data = self._post("/developer/walletSets", {
            "idempotencyKey": str(uuid.uuid4()),
            "name": name,
            "entitySecretCiphertext": self.entity_secret,
        })
        wallet_set_id = data.get("walletSet", {}).get("id", "")
        logger.info(f"Created wallet set: {wallet_set_id}")
        return wallet_set_id

    def create_wallet(self, wallet_set_id: str, blockchain: str = "ARC-TESTNET") -> AgentWallet:
        """Create a single wallet in the given wallet set."""
        data = self._post("/developer/wallets", {
            "idempotencyKey": str(uuid.uuid4()),
            "walletSetId": wallet_set_id,
            "blockchains": [blockchain],
            "count": 1,
            "accountType": "EOA",
            "entitySecretCiphertext": self.entity_secret,
        })
        wallet = data.get("wallets", [{}])[0]
        return AgentWallet(
            wallet_id=wallet.get("id", ""),
            wallet_set_id=wallet_set_id,
            address=wallet.get("address", ""),
            blockchain=blockchain,
            model_name="",
        )

    def get_balance(self, wallet_id: str) -> list[dict]:
        """Get token balances for a wallet."""
        data = self._get(f"/wallets/{wallet_id}/balances")
        return data.get("tokenBalances", [])

    def transfer_usdc(self, from_wallet_id: str, to_address: str, amount: str) -> str:
        """Transfer USDC from a dev-controlled wallet. Returns transaction ID."""
        data = self._post("/developer/transactions/transfer", {
            "idempotencyKey": str(uuid.uuid4()),
            "walletId": from_wallet_id,
            "tokenAddress": get_usdc_address(),
            "destinationAddress": to_address,
            "amounts": [amount],
            "feeLevel": "MEDIUM",
            "entitySecretCiphertext": self.entity_secret,
        })
        return data.get("id", "")

    def contract_call(self, wallet_id: str, contract_address: str, abi_fn: str, args: list) -> str:
        """Execute a smart contract function from a dev-controlled wallet."""
        data = self._post("/developer/transactions/contractExecution", {
            "idempotencyKey": str(uuid.uuid4()),
            "walletId": wallet_id,
            "contractAddress": contract_address,
            "abiFunctionSignature": abi_fn,
            "abiParameters": args,
            "feeLevel": "MEDIUM",
            "entitySecretCiphertext": self.entity_secret,
        })
        return data.get("id", "")


def get_usdc_address(network: str = "ARC-TESTNET") -> str:
    """USDC contract address on Arc. Update after checking Circle docs."""
    # Placeholder — replace with actual deployed USDC address on Arc
    addresses = {
        "ARC-TESTNET": os.environ.get("USDC_CONTRACT_ADDRESS", ""),
        "ARC": os.environ.get("USDC_CONTRACT_ADDRESS", ""),
    }
    return addresses.get(network, "")


def create_agent_wallets(model_names: list[str], blockchain: str = "ARC-TESTNET") -> dict[str, AgentWallet]:
    """
    Create one dev-controlled wallet per trading agent.
    Returns {model_name: AgentWallet}.
    """
    client = CircleClient()
    wallet_set_id = client.create_wallet_set("CGAE Trading Agents")

    wallets = {}
    for name in model_names:
        wallet = client.create_wallet(wallet_set_id, blockchain)
        wallet.model_name = name
        wallets[name] = wallet
        logger.info(f"Wallet for {name}: {wallet.address}")

    return wallets


# ─── Paymaster ────────────────────────────────────────────────────────────────

PAYMASTER_INFO = """
Circle Paymaster allows agents to pay gas fees in USDC instead of native tokens.

On Arc, the Paymaster contract is deployed at a known address. When submitting
UserOperations (ERC-4337), set the paymasterAndData field to the Circle Paymaster
address. The paymaster deducts USDC from the agent's wallet for gas.

Integration: Use Circle Modular Wallets (SCA) with the Paymaster for gasless UX.
For dev-controlled EOA wallets, the agent needs native tokens OR can use
Circle's Gas Station to sponsor transactions.
"""


# ─── USYC (Idle Capital Yield) ────────────────────────────────────────────────

@dataclass
class USYCAllocation:
    agent_name: str
    amount_usdc: float
    usyc_shares: float
    apy_estimate: float


class USYCManager:
    """
    Manages USYC allocations for idle trading capital.

    USYC is a tokenized money market fund. Agents park idle USDC in USYC
    between trades to earn yield, then redeem when they need to open positions.
    """

    def __init__(self, usyc_address: Optional[str] = None):
        self.usyc_address = usyc_address or os.environ.get("USYC_CONTRACT_ADDRESS", "")
        self.allocations: dict[str, USYCAllocation] = {}

    def deposit(self, agent_name: str, amount_usdc: float) -> USYCAllocation:
        """
        Deposit idle USDC into USYC for yield.
        In production, this calls the USYC contract's deposit function.
        """
        # USYC is ~1:1 with USDC (money market fund)
        apy = 0.045  # ~4.5% APY estimate
        shares = amount_usdc  # simplified 1:1 for hackathon

        alloc = USYCAllocation(
            agent_name=agent_name,
            amount_usdc=amount_usdc,
            usyc_shares=shares,
            apy_estimate=apy,
        )
        self.allocations[agent_name] = alloc
        logger.info(f"[USYC] {agent_name} deposited ${amount_usdc:.2f} → {shares:.2f} USYC shares ({apy*100:.1f}% APY)")
        return alloc

    def withdraw(self, agent_name: str, shares: Optional[float] = None) -> float:
        """Redeem USYC shares back to USDC for trading."""
        alloc = self.allocations.get(agent_name)
        if not alloc:
            return 0.0

        redeem = shares or alloc.usyc_shares
        usdc_out = redeem  # 1:1 simplified
        alloc.usyc_shares -= redeem
        alloc.amount_usdc -= usdc_out

        if alloc.usyc_shares <= 0:
            del self.allocations[agent_name]

        logger.info(f"[USYC] {agent_name} redeemed {redeem:.2f} shares → ${usdc_out:.2f} USDC")
        return usdc_out

    def total_yield_estimate(self, days: float = 1.0) -> dict[str, float]:
        """Estimate yield earned across all allocations."""
        yields = {}
        for name, alloc in self.allocations.items():
            daily_yield = alloc.amount_usdc * (alloc.apy_estimate / 365) * days
            yields[name] = daily_yield
        return yields

    def summary(self) -> list[dict]:
        return [
            {
                "agent": a.agent_name,
                "deposited_usdc": a.amount_usdc,
                "usyc_shares": a.usyc_shares,
                "apy": a.apy_estimate,
            }
            for a in self.allocations.values()
        ]
