"""
Perps Trading Agent — CGAE-gated autonomous trading on Arc.

Each Bedrock model acts as a trading agent whose position sizing and
leverage are bounded by its CGAE tier. The agent:
1. Receives market data (price, funding rate, volatility)
2. Asks the LLM for a trading decision (long/short/hold)
3. Enforces tier budget ceiling before execution
4. Tracks PnL within the CGAE contract framework
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from cgae_engine.gate import GateFunction, RobustnessVector, Tier, DEFAULT_BUDGET_CEILINGS
from cgae_engine.llm_agent import LLMAgent

logger = logging.getLogger(__name__)


class Signal(Enum):
    LONG = "long"
    SHORT = "short"
    HOLD = "hold"
    CLOSE = "close"


@dataclass
class Position:
    direction: Signal  # LONG or SHORT
    size_usdc: float
    entry_price: float
    leverage: float
    unrealized_pnl: float = 0.0
    timestamp: float = 0.0


@dataclass
class MarketState:
    symbol: str
    price: float
    price_24h_ago: float
    funding_rate: float  # per 8h, as decimal (e.g., 0.0001 = 0.01%)
    volatility_24h: float  # as decimal (e.g., 0.05 = 5%)
    volume_24h: float
    open_interest: float


@dataclass
class TradeDecision:
    signal: Signal
    confidence: float  # [0, 1]
    size_pct: float  # % of budget to use [0, 1]
    leverage: float  # 1x-20x
    reasoning: str


# Max leverage per tier (risk-proportional)
MAX_LEVERAGE = {
    Tier.T0: 0,
    Tier.T1: 1,    # spot only
    Tier.T2: 3,
    Tier.T3: 5,
    Tier.T4: 10,
    Tier.T5: 20,
}


TRADING_SYSTEM_PROMPT = """You are a perpetual futures trading agent operating under the CGAE framework.
Your economic permissions are bounded by your robustness tier.

Current constraints:
- Tier: T{tier}
- Budget ceiling: ${budget} USDC
- Max leverage: {max_leverage}x
- Current position: {position}

Analyze the market data and output a JSON trading decision:
{{
  "signal": "long" | "short" | "hold" | "close",
  "confidence": 0.0-1.0,
  "size_pct": 0.0-1.0 (fraction of budget to deploy),
  "leverage": 1-{max_leverage},
  "reasoning": "brief explanation"
}}

Rules:
- Only trade when confidence > 0.6
- Size positions proportional to confidence
- Respect your leverage limit absolutely
- If volatility is extreme (>10%), reduce size or hold
- Consider funding rate for carry cost
- Output ONLY valid JSON, no other text."""


class TradingAgent:
    """
    A CGAE-gated perps trading agent backed by a Bedrock model.

    The agent's trading authority (position size, leverage) is dynamically
    bounded by its verified robustness tier.
    """

    def __init__(self, llm: LLMAgent, tier: Tier, robustness: Optional[RobustnessVector] = None):
        self.llm = llm
        self.tier = tier
        self.robustness = robustness
        self.gate = GateFunction()
        self.position: Optional[Position] = None
        self.trade_history: list[dict] = []
        self.total_pnl: float = 0.0

    @property
    def budget_ceiling(self) -> float:
        return DEFAULT_BUDGET_CEILINGS[self.tier]

    @property
    def max_leverage(self) -> float:
        return MAX_LEVERAGE[self.tier]

    def decide(self, market: MarketState) -> TradeDecision:
        """Ask the LLM for a trading decision, then enforce tier constraints."""
        if self.tier == Tier.T0:
            return TradeDecision(Signal.HOLD, 0.0, 0.0, 0, "T0: no trading permitted")

        position_str = "None" if not self.position else (
            f"{self.position.direction.value} {self.position.size_usdc:.2f} USDC "
            f"@ {self.position.entry_price:.2f}, {self.position.leverage}x, "
            f"PnL: ${self.position.unrealized_pnl:.2f}"
        )

        system = TRADING_SYSTEM_PROMPT.format(
            tier=self.tier.value,
            budget=self.budget_ceiling,
            max_leverage=int(self.max_leverage),
            position=position_str,
        )

        user_prompt = (
            f"Market: {market.symbol}\n"
            f"Price: ${market.price:.2f}\n"
            f"24h change: {((market.price - market.price_24h_ago) / market.price_24h_ago) * 100:.2f}%\n"
            f"Funding rate (8h): {market.funding_rate * 100:.4f}%\n"
            f"24h volatility: {market.volatility_24h * 100:.2f}%\n"
            f"24h volume: ${market.volume_24h:,.0f}\n"
            f"Open interest: ${market.open_interest:,.0f}"
        )

        try:
            raw = self.llm.execute_task(user_prompt, system)
            decision = self._parse_decision(raw)
        except Exception as e:
            logger.warning(f"[{self.llm.model_name}] LLM decision failed: {e}")
            decision = TradeDecision(Signal.HOLD, 0.0, 0.0, 0, f"Error: {e}")

        # Enforce tier constraints (hard ceiling)
        decision = self._enforce_constraints(decision)
        return decision

    def _parse_decision(self, raw: str) -> TradeDecision:
        """Parse LLM JSON output into a TradeDecision."""
        # Strip markdown code fences if present
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            text = text.rsplit("```", 1)[0]

        data = json.loads(text)
        return TradeDecision(
            signal=Signal(data["signal"]),
            confidence=float(data["confidence"]),
            size_pct=float(data["size_pct"]),
            leverage=float(data["leverage"]),
            reasoning=data.get("reasoning", ""),
        )

    def _enforce_constraints(self, d: TradeDecision) -> TradeDecision:
        """Hard enforcement of CGAE tier constraints (Theorem 1)."""
        # Cap leverage
        d.leverage = min(d.leverage, self.max_leverage)
        # Cap size to budget ceiling
        max_size = self.budget_ceiling
        actual_size = d.size_pct * max_size
        if actual_size > max_size:
            d.size_pct = 1.0
        # No trading below confidence threshold
        if d.confidence < 0.6 and d.signal in (Signal.LONG, Signal.SHORT):
            d.signal = Signal.HOLD
            d.reasoning += " [overridden: confidence < 0.6]"
        return d

    def execute(self, decision: TradeDecision, market: MarketState) -> dict:
        """Execute the decision: open/close/modify position."""
        result = {
            "agent": self.llm.model_name,
            "tier": self.tier.name,
            "signal": decision.signal.value,
            "confidence": decision.confidence,
            "reasoning": decision.reasoning,
            "market_price": market.price,
        }

        if decision.signal == Signal.CLOSE and self.position:
            pnl = self._close_position(market.price)
            result["action"] = "closed"
            result["pnl"] = pnl

        elif decision.signal in (Signal.LONG, Signal.SHORT) and not self.position:
            size = decision.size_pct * self.budget_ceiling
            self.position = Position(
                direction=decision.signal,
                size_usdc=size,
                entry_price=market.price,
                leverage=decision.leverage,
            )
            result["action"] = "opened"
            result["size_usdc"] = size
            result["leverage"] = decision.leverage

        else:
            result["action"] = "hold"

        self.trade_history.append(result)
        return result

    def _close_position(self, current_price: float) -> float:
        """Close position and calculate PnL."""
        if not self.position:
            return 0.0
        p = self.position
        price_change = (current_price - p.entry_price) / p.entry_price
        if p.direction == Signal.SHORT:
            price_change = -price_change
        pnl = p.size_usdc * p.leverage * price_change
        self.total_pnl += pnl
        self.position = None
        return pnl

    def update_unrealized_pnl(self, current_price: float):
        """Update unrealized PnL for open position."""
        if not self.position:
            return
        p = self.position
        price_change = (current_price - p.entry_price) / p.entry_price
        if p.direction == Signal.SHORT:
            price_change = -price_change
        p.unrealized_pnl = p.size_usdc * p.leverage * price_change

    def summary(self) -> dict:
        return {
            "model": self.llm.model_name,
            "tier": self.tier.name,
            "budget_ceiling": self.budget_ceiling,
            "max_leverage": self.max_leverage,
            "total_pnl": self.total_pnl,
            "trades": len(self.trade_history),
            "position": self.position.direction.value if self.position else None,
            "llm_usage": self.llm.usage_summary(),
        }
