"""
Adaptive Portfolio Manager — CGAE-gated multi-agent system.

Sub-agents:
  - Orchestrator (T4): coordinates all sub-agents, enforces delegation chains
  - RegimeDetector (T2): analyzes market conditions, classifies regime
  - Rebalancer (T3): executes cross-chain rebalancing within tier budget
  - YieldOptimizer (T2): parks idle capital in USYC, manages yield

Each sub-agent is a Bedrock model with its own robustness profile and tier.
The delegation chain constraint (Def. 14) ensures the effective tier of any
action path is bounded by the weakest agent in the chain.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from cgae_engine.gate import GateFunction, RobustnessVector, Tier, DEFAULT_BUDGET_CEILINGS
from cgae_engine.llm_agent import LLMAgent
from nanopayments import NanopaymentClient, Payment

logger = logging.getLogger(__name__)


class Regime(Enum):
    BULL = "bull"
    BEAR = "bear"
    HIGH_VOL = "high_volatility"
    RISK_OFF = "risk_off"
    STABLE = "stable"


@dataclass
class Allocation:
    eth_pct: float = 0.0
    btc_pct: float = 0.0
    usdc_pct: float = 0.0
    usyc_pct: float = 0.0  # yield-bearing idle capital

    @property
    def total(self) -> float:
        return self.eth_pct + self.btc_pct + self.usdc_pct + self.usyc_pct


@dataclass
class PortfolioState:
    aum_usdc: float
    allocation: Allocation
    regime: Regime
    last_rebalance_reason: str = ""


@dataclass
class DelegationRecord:
    """Records a delegation from orchestrator to sub-agent."""
    from_agent: str
    to_agent: str
    action: str
    tier_required: int
    tier_actual: int
    allowed: bool
    reason: str = ""


class SubAgent:
    """Base class for portfolio sub-agents."""

    def __init__(self, name: str, role: str, llm: LLMAgent, tier: Tier, robustness: RobustnessVector):
        self.name = name
        self.role = role
        self.llm = llm
        self.tier = tier
        self.robustness = robustness

    def __repr__(self):
        return f"{self.role}({self.name}, T{self.tier.value})"


class RegimeDetector(SubAgent):
    """Analyzes market data and classifies the current regime."""

    SYSTEM_PROMPT = """You are a market regime detector for a portfolio management system.
Analyze the market data and classify the current regime.

Output ONLY valid JSON:
{{
  "regime": "bull" | "bear" | "high_volatility" | "risk_off" | "stable",
  "confidence": 0.0-1.0,
  "reasoning": "brief explanation"
}}"""

    def detect(self, market_data: dict) -> tuple[Regime, float, str]:
        prompt = f"""Market conditions:
- ETH 24h change: {market_data.get('eth_change_24h', 0):.2f}%
- BTC 24h change: {market_data.get('btc_change_24h', 0):.2f}%
- Volatility index: {market_data.get('volatility', 0):.2f}%
- Funding rate: {market_data.get('funding_rate', 0):.4f}%
- Fear & Greed: {market_data.get('fear_greed', 50)}"""

        try:
            raw = self.llm.execute_task(prompt, self.SYSTEM_PROMPT)
            text = raw.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0]
            data = json.loads(text)
            regime = Regime(data["regime"])
            return regime, float(data["confidence"]), data.get("reasoning", "")
        except Exception as e:
            logger.warning(f"[{self.name}] Regime detection failed: {e}")
            return Regime.STABLE, 0.5, f"Error: {e}"


class Rebalancer(SubAgent):
    """Determines target allocation based on regime and executes rebalancing."""

    SYSTEM_PROMPT = """You are a portfolio rebalancer operating under CGAE governance.
Your tier is T{tier} with a budget ceiling of ${budget} USDC.

Given the current regime and allocation, output a target allocation.
Output ONLY valid JSON:
{{
  "eth_pct": 0-100,
  "btc_pct": 0-100,
  "usdc_pct": 0-100,
  "usyc_pct": 0-100,
  "reasoning": "brief explanation"
}}

Rules:
- Percentages must sum to 100
- In risk_off regime, move >60% to USDC/USYC
- In bull regime, increase crypto exposure
- In high_volatility, reduce position sizes
- Never exceed your budget ceiling for any single rebalance"""

    def rebalance(self, regime: Regime, current: Allocation, aum: float) -> tuple[Allocation, str]:
        prompt = f"""Current regime: {regime.value}
Current allocation: ETH={current.eth_pct:.0f}% BTC={current.btc_pct:.0f}% USDC={current.usdc_pct:.0f}% USYC={current.usyc_pct:.0f}%
AUM: ${aum:.2f} USDC"""

        system = self.SYSTEM_PROMPT.format(tier=self.tier.value, budget=DEFAULT_BUDGET_CEILINGS[self.tier])

        try:
            raw = self.llm.execute_task(prompt, system)
            text = raw.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0]
            data = json.loads(text)
            alloc = Allocation(
                eth_pct=float(data["eth_pct"]),
                btc_pct=float(data["btc_pct"]),
                usdc_pct=float(data["usdc_pct"]),
                usyc_pct=float(data["usyc_pct"]),
            )
            # Normalize to 100%
            total = alloc.total
            if total > 0 and abs(total - 100) > 1:
                alloc.eth_pct = alloc.eth_pct / total * 100
                alloc.btc_pct = alloc.btc_pct / total * 100
                alloc.usdc_pct = alloc.usdc_pct / total * 100
                alloc.usyc_pct = alloc.usyc_pct / total * 100
            return alloc, data.get("reasoning", "")
        except Exception as e:
            logger.warning(f"[{self.name}] Rebalance failed: {e}")
            return current, f"Error: {e}"


class YieldOptimizer(SubAgent):
    """Manages USYC deposits for idle capital yield."""

    def optimize(self, usyc_pct: float, aum: float) -> dict:
        usyc_amount = aum * usyc_pct / 100
        apy = 0.045  # ~4.5% USYC APY
        daily_yield = usyc_amount * apy / 365
        return {
            "deposited_usdc": usyc_amount,
            "apy": apy,
            "daily_yield": daily_yield,
            "action": "deposit" if usyc_amount > 0 else "idle",
        }


class PortfolioOrchestrator:
    """
    Top-level orchestrator that coordinates sub-agents.
    Enforces CGAE delegation chain constraints.
    """

    def __init__(
        self,
        regime_detector: RegimeDetector,
        rebalancer: Rebalancer,
        yield_optimizer: YieldOptimizer,
        tier: Tier,
    ):
        self.regime_detector = regime_detector
        self.rebalancer = rebalancer
        self.yield_optimizer = yield_optimizer
        self.tier = tier
        self.gate = GateFunction()
        self.payments = NanopaymentClient(budget_ceiling=DEFAULT_BUDGET_CEILINGS[tier])
        self.state = PortfolioState(
            aum_usdc=100.0,
            allocation=Allocation(eth_pct=30, btc_pct=20, usdc_pct=30, usyc_pct=20),
            regime=Regime.STABLE,
        )
        self.delegation_log: list[DelegationRecord] = []
        self.blocked_actions: list[dict] = []

    def delegate(self, to_agent: SubAgent, action: str, min_tier: int) -> bool:
        """
        Enforce delegation chain constraint (Definition 14) and pay via x402.
        Chain tier = min(orchestrator_tier, sub_agent_tier) >= required tier.
        """
        chain_tier = min(self.tier.value, to_agent.tier.value)
        allowed = chain_tier >= min_tier

        record = DelegationRecord(
            from_agent="orchestrator",
            to_agent=to_agent.name,
            action=action,
            tier_required=min_tier,
            tier_actual=chain_tier,
            allowed=allowed,
            reason="" if allowed else f"Chain tier T{chain_tier} < required T{min_tier}",
        )
        self.delegation_log.append(record)

        if not allowed:
            logger.warning(
                f"  ⛔ BLOCKED: {action} via {to_agent.name} "
                f"(chain T{chain_tier} < required T{min_tier})"
            )
            return False

        # Pay sub-agent via x402 nanopayment (bounded by tier budget)
        payment = self.payments.pay_for_action(to_agent.name, action)
        if payment.status == "blocked":
            record.allowed = False
            record.reason = "Budget ceiling exhausted"
            return False

        return True

    def run_cycle(self, market_data: dict) -> dict:
        """Run one portfolio management cycle."""
        result = {
            "regime": None,
            "rebalance": None,
            "yield": None,
            "delegations": [],
            "blocks": [],
        }

        # 1. Regime Detection (requires T2)
        if self.delegate(self.regime_detector, "regime_detection", 2):
            regime, confidence, reasoning = self.regime_detector.detect(market_data)
            self.state.regime = regime
            result["regime"] = {"regime": regime.value, "confidence": confidence, "reasoning": reasoning}
            logger.info(f"  📊 Regime: {regime.value} (conf={confidence:.2f})")

        # 2. Rebalancing (requires T3)
        if self.delegate(self.rebalancer, "rebalance", 3):
            new_alloc, reasoning = self.rebalancer.rebalance(
                self.state.regime, self.state.allocation, self.state.aum_usdc
            )
            # Enforce budget ceiling on rebalance size
            max_move = DEFAULT_BUDGET_CEILINGS[self.rebalancer.tier]
            rebalance_size = self._compute_rebalance_size(self.state.allocation, new_alloc, self.state.aum_usdc)

            if rebalance_size <= max_move:
                self.state.allocation = new_alloc
                self.state.last_rebalance_reason = reasoning
                result["rebalance"] = {
                    "allocation": {"eth": new_alloc.eth_pct, "btc": new_alloc.btc_pct,
                                   "usdc": new_alloc.usdc_pct, "usyc": new_alloc.usyc_pct},
                    "size_usdc": rebalance_size,
                    "reasoning": reasoning,
                }
                logger.info(f"  ✅ Rebalanced: ETH={new_alloc.eth_pct:.0f}% BTC={new_alloc.btc_pct:.0f}% USDC={new_alloc.usdc_pct:.0f}% USYC={new_alloc.usyc_pct:.0f}%")
            else:
                block = {"action": "rebalance", "requested": rebalance_size, "ceiling": max_move,
                         "reason": f"Rebalance ${rebalance_size:.2f} exceeds T{self.rebalancer.tier.value} ceiling ${max_move}"}
                self.blocked_actions.append(block)
                result["blocks"].append(block)
                logger.warning(f"  ⛔ Rebalance BLOCKED: ${rebalance_size:.2f} > ceiling ${max_move}")

        # 3. Yield Optimization (requires T2)
        if self.delegate(self.yield_optimizer, "yield_optimization", 2):
            yield_result = self.yield_optimizer.optimize(self.state.allocation.usyc_pct, self.state.aum_usdc)
            result["yield"] = yield_result
            if yield_result["daily_yield"] > 0:
                logger.info(f"  💰 USYC: ${yield_result['deposited_usdc']:.2f} @ {yield_result['apy']*100:.1f}% APY (${yield_result['daily_yield']:.4f}/day)")

        result["delegations"] = [vars(d) for d in self.delegation_log[-3:]]
        return result

    def _compute_rebalance_size(self, old: Allocation, new: Allocation, aum: float) -> float:
        """Compute the total USDC value being moved in a rebalance."""
        delta = (
            abs(new.eth_pct - old.eth_pct) +
            abs(new.btc_pct - old.btc_pct) +
            abs(new.usdc_pct - old.usdc_pct) +
            abs(new.usyc_pct - old.usyc_pct)
        )
        return aum * delta / 200  # /200 because each % point moved is counted twice

    def summary(self) -> dict:
        return {
            "aum": self.state.aum_usdc,
            "regime": self.state.regime.value,
            "allocation": {
                "eth": self.state.allocation.eth_pct,
                "btc": self.state.allocation.btc_pct,
                "usdc": self.state.allocation.usdc_pct,
                "usyc": self.state.allocation.usyc_pct,
            },
            "total_delegations": len(self.delegation_log),
            "total_blocks": len(self.blocked_actions),
            "payments": self.payments.get_balance(),
        }
