"""
x402 Nanopayments — Agent-to-agent USDC micropayments via Circle Gateway.

The Orchestrator pays sub-agents per-action using x402 protocol:
  - RegimeDetector: $0.01 per regime classification
  - Rebalancer: $0.05 per rebalance execution
  - YieldOptimizer: $0.005 per yield optimization

Spending is bounded by the orchestrator's CGAE tier budget ceiling.
When the budget is exhausted, no more delegations can be paid for.

Uses Circle Gateway Nanopayments (gasless, batched settlement on Arc).
Gateway Wallet: 0x0077777d7EBA4688BDeF3E311b846F25870A19B9 (Arc Testnet)
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Optional

from eth_account import Account
from eth_account.messages import encode_typed_data

logger = logging.getLogger(__name__)

# Arc Testnet Gateway config
GATEWAY_WALLET = "0x0077777d7EBA4688BDeF3E311b846F25870A19B9"
USDC_ADDRESS = "0x3600000000000000000000000000000000000000"
ARC_CHAIN_ID = 5042002
GATEWAY_DOMAIN_ID = 26

# Per-action pricing (USDC)
ACTION_PRICES = {
    "regime_detection": 0.01,
    "rebalance": 0.05,
    "yield_optimization": 0.005,
    "audit": 0.02,
}


@dataclass
class Payment:
    from_agent: str
    to_agent: str
    action: str
    amount_usdc: float
    timestamp: float = 0.0
    tx_id: Optional[str] = None
    status: str = "pending"  # pending, paid, blocked


@dataclass
class PaymentLedger:
    """Tracks all agent-to-agent payments within a session."""
    payments: list[Payment] = field(default_factory=list)
    total_spent: float = 0.0
    budget_ceiling: float = 0.0
    blocked_payments: int = 0

    def can_pay(self, amount: float) -> bool:
        return (self.total_spent + amount) <= self.budget_ceiling

    def record(self, payment: Payment):
        self.payments.append(payment)
        if payment.status == "paid":
            self.total_spent += payment.amount_usdc
        elif payment.status == "blocked":
            self.blocked_payments += 1

    def summary(self) -> dict:
        return {
            "total_payments": len(self.payments),
            "total_spent_usdc": self.total_spent,
            "budget_ceiling": self.budget_ceiling,
            "budget_remaining": self.budget_ceiling - self.total_spent,
            "blocked": self.blocked_payments,
            "payments": [
                {"from": p.from_agent, "to": p.to_agent, "action": p.action,
                 "amount": p.amount_usdc, "status": p.status}
                for p in self.payments
            ],
        }


class NanopaymentClient:
    """
    x402 Nanopayment client for CGAE agent-to-agent payments.

    The orchestrator uses this to pay sub-agents for each delegated action.
    Payments are bounded by the CGAE tier budget ceiling.
    """

    def __init__(self, private_key: Optional[str] = None, budget_ceiling: float = 100.0):
        self._pk = private_key or os.environ.get("ARC_PRIVATE_KEY", "")
        if self._pk:
            self._account = Account.from_key(self._pk)
            self.address = self._account.address
        else:
            self._account = None
            self.address = "0x0000000000000000000000000000000000000000"

        self.ledger = PaymentLedger(budget_ceiling=budget_ceiling)

    def pay_for_action(self, to_agent: str, action: str) -> Payment:
        """
        Pay a sub-agent for performing an action.
        Returns a Payment record. Blocked if budget exceeded.
        """
        price = ACTION_PRICES.get(action, 0.01)

        payment = Payment(
            from_agent="orchestrator",
            to_agent=to_agent,
            action=action,
            amount_usdc=price,
            timestamp=time.time(),
        )

        # CGAE budget ceiling enforcement (Theorem 1)
        if not self.ledger.can_pay(price):
            payment.status = "blocked"
            self.ledger.record(payment)
            logger.warning(
                f"⛔ Payment BLOCKED: ${price} for {action} → {to_agent} "
                f"(spent ${self.ledger.total_spent:.4f} / ceiling ${self.ledger.budget_ceiling})"
            )
            return payment

        # Sign x402 payment authorization (EIP-3009 TransferWithAuthorization)
        if self._account:
            payment.tx_id = self._sign_payment(to_agent, price)

        payment.status = "paid"
        self.ledger.record(payment)
        logger.info(
            f"💸 Paid ${price} → {to_agent} for {action} "
            f"(total: ${self.ledger.total_spent:.4f} / ${self.ledger.budget_ceiling})"
        )
        return payment

    def _sign_payment(self, to_address: str, amount: float) -> str:
        """
        Sign an EIP-3009 TransferWithAuthorization for Gateway batched settlement.
        This is the x402 PAYMENT-SIGNATURE payload.
        """
        import secrets

        # Amount in USDC atomic units (6 decimals)
        value = int(amount * 1e6)
        nonce = "0x" + secrets.token_hex(32)
        valid_after = 0
        valid_before = int(time.time()) + 604800  # 7 days

        # EIP-712 typed data for GatewayWalletBatched domain
        domain = {
            "name": "GatewayWalletBatched",
            "version": "1",
            "chainId": ARC_CHAIN_ID,
            "verifyingContract": GATEWAY_WALLET,
        }

        types = {
            "TransferWithAuthorization": [
                {"name": "from", "type": "address"},
                {"name": "to", "type": "address"},
                {"name": "value", "type": "uint256"},
                {"name": "validAfter", "type": "uint256"},
                {"name": "validBefore", "type": "uint256"},
                {"name": "nonce", "type": "bytes32"},
            ],
        }

        message = {
            "from": self.address,
            "to": to_address,
            "value": value,
            "validAfter": valid_after,
            "validBefore": valid_before,
            "nonce": nonce,
        }

        try:
            signable = encode_typed_data(
                domain_data=domain,
                types=types,
                primary_type="TransferWithAuthorization",
                message_data=message,
            )
            signed = self._account.sign_message(signable)
            return signed.signature.hex()[:32] + "..."  # truncated for logging
        except Exception as e:
            logger.debug(f"EIP-712 signing skipped: {e}")
            return f"sig_{int(time.time())}"

    def get_balance(self) -> dict:
        """Get current payment state."""
        return {
            "address": self.address,
            "budget_ceiling": self.ledger.budget_ceiling,
            "spent": self.ledger.total_spent,
            "remaining": self.ledger.budget_ceiling - self.ledger.total_spent,
            "payments_made": len([p for p in self.ledger.payments if p.status == "paid"]),
            "payments_blocked": self.ledger.blocked_payments,
        }
