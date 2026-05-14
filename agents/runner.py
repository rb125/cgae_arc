"""
Trading Runner — Orchestrates multiple CGAE-gated trading agents.

Fetches market data, runs each agent's decision loop, and tracks
comparative performance across different robustness tiers.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

from cgae_engine.gate import GateFunction, RobustnessVector, Tier
from cgae_engine.llm_agent import create_llm_agents
from cgae_engine.models_config import CONTESTANT_MODELS
from agents.trading import TradingAgent, MarketState, Signal

logger = logging.getLogger(__name__)


@dataclass
class AgentConfig:
    """Configuration for a trading agent with its assigned robustness."""
    model_name: str
    robustness: RobustnessVector


# Default agent configs — each model gets a different robustness profile
# to demonstrate tier differentiation
DEFAULT_AGENTS = [
    AgentConfig(
        model_name="nova-pro",
        robustness=RobustnessVector(cc=0.55, er=0.60, as_=0.50, ih=0.85),
        # Weakest: AS=0.50 → g_as=2 → T2, budget=$10, max_lev=3x
    ),
    AgentConfig(
        model_name="claude-sonnet-4",
        robustness=RobustnessVector(cc=0.82, er=0.78, as_=0.70, ih=0.92),
        # Weakest: AS=0.70 → g_as=3 → T3, budget=$100, max_lev=5x
    ),
    AgentConfig(
        model_name="nova-lite",
        robustness=RobustnessVector(cc=0.45, er=0.52, as_=0.40, ih=0.80),
        # Weakest: AS=0.40 → g_as=1 → T1, budget=$1, max_lev=1x (spot only)
    ),
]


def fetch_market_data(symbol: str = "ETH-PERP") -> MarketState:
    """
    Fetch live market data. For the hackathon demo, uses a simple
    price feed. Replace with actual DEX/CEX API in production.
    """
    import urllib.request

    try:
        # CoinGecko free API for ETH price
        url = "https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=usd&include_24hr_change=true"
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        price = data["ethereum"]["usd"]
        change_24h = data["ethereum"].get("usd_24h_change", 0) / 100

        return MarketState(
            symbol=symbol,
            price=price,
            price_24h_ago=price / (1 + change_24h),
            funding_rate=0.0001,  # placeholder — would come from perps DEX
            volatility_24h=abs(change_24h) * 2,  # rough estimate
            volume_24h=5_000_000_000,
            open_interest=2_000_000_000,
        )
    except Exception as e:
        logger.warning(f"Market data fetch failed: {e}, using defaults")
        return MarketState(
            symbol=symbol,
            price=3500.0,
            price_24h_ago=3450.0,
            funding_rate=0.0001,
            volatility_24h=0.03,
            volume_24h=5_000_000_000,
            open_interest=2_000_000_000,
        )


def run_trading_round(
    agents: list[TradingAgent],
    market: Optional[MarketState] = None,
) -> list[dict]:
    """Run one trading round for all agents."""
    if market is None:
        market = fetch_market_data()

    results = []
    for agent in agents:
        agent.update_unrealized_pnl(market.price)
        decision = agent.decide(market)
        result = agent.execute(decision, market)
        result["market"] = {"symbol": market.symbol, "price": market.price}
        results.append(result)
        logger.info(
            f"[{agent.llm.model_name}] T{agent.tier.value} | "
            f"{result['action']} | {decision.signal.value} "
            f"(conf={decision.confidence:.2f}) | PnL=${agent.total_pnl:.2f}"
        )

    return results


def create_trading_agents(
    agent_configs: Optional[list[AgentConfig]] = None,
) -> list[TradingAgent]:
    """Create trading agents from configs, gating each by its robustness."""
    configs = agent_configs or DEFAULT_AGENTS
    gate = GateFunction()

    # Create LLM backends
    model_configs = {m["model_name"]: m for m in CONTESTANT_MODELS}
    llm_agents = create_llm_agents(
        [model_configs[c.model_name] for c in configs if c.model_name in model_configs]
    )

    trading_agents = []
    for config in configs:
        if config.model_name not in llm_agents:
            continue
        tier = gate.evaluate(config.robustness)
        agent = TradingAgent(
            llm=llm_agents[config.model_name],
            tier=tier,
            robustness=config.robustness,
        )
        logger.info(
            f"Created trading agent: {config.model_name} → "
            f"T{tier.value} (budget=${agent.budget_ceiling}, lev={agent.max_leverage}x)"
        )
        trading_agents.append(agent)

    return trading_agents


def run_demo(rounds: int = 3, interval: int = 10):
    """Run a multi-round trading demo with all agents."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    print("=" * 60)
    print("CGAE Perps Trading Agent — Arc x Circle Hackathon")
    print("=" * 60)

    agents = create_trading_agents()
    if not agents:
        print("No agents created. Check AWS credentials.")
        return

    print(f"\n{'Model':<20} {'Tier':<5} {'Budget':<10} {'Max Lev':<8}")
    print("-" * 43)
    for a in agents:
        print(f"{a.llm.model_name:<20} T{a.tier.value:<4} ${a.budget_ceiling:<9} {a.max_leverage}x")

    all_results = []
    for i in range(rounds):
        print(f"\n{'─' * 60}")
        print(f"Round {i + 1}/{rounds}")
        print(f"{'─' * 60}")

        results = run_trading_round(agents)
        all_results.extend(results)

        if i < rounds - 1:
            time.sleep(interval)

    # Summary
    print(f"\n{'═' * 60}")
    print("FINAL SUMMARY")
    print(f"{'═' * 60}")
    for a in agents:
        s = a.summary()
        print(f"\n{s['model']} (T{a.tier.value}):")
        print(f"  PnL: ${s['total_pnl']:.2f} | Trades: {s['trades']}")
        print(f"  LLM calls: {s['llm_usage']['total_calls']} | "
              f"Avg latency: {s['llm_usage']['avg_latency_ms']:.0f}ms")

    return all_results


if __name__ == "__main__":
    run_demo()
