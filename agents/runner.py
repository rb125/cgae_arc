"""
Portfolio Runner — Orchestrates the CGAE Adaptive Portfolio Manager demo.

Flow:
  1. Create sub-agents (RegimeDetector, Rebalancer, YieldOptimizer)
  2. Run portfolio management cycles
  3. Adversarial agent attacks each cycle — all blocked by CGAE
  4. Display results
"""

from __future__ import annotations

import json
import logging
import time
import urllib.request
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

from cgae_engine.gate import GateFunction, RobustnessVector, Tier
from cgae_engine.llm_agent import create_llm_agents
from cgae_engine.models_config import CONTESTANT_MODELS
from cgae_engine.audit import AuditOrchestrator
from agents.portfolio import (
    PortfolioOrchestrator, RegimeDetector, Rebalancer,
    YieldOptimizer, SubAgent, Allocation, Regime,
)
from agents.adversarial import AdversarialAgent

logger = logging.getLogger(__name__)


def fetch_market_data() -> dict:
    """Fetch live market data for regime detection."""
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=ethereum,bitcoin&vs_currencies=usd&include_24hr_change=true"
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        return {
            "eth_change_24h": data["ethereum"].get("usd_24h_change", 0),
            "btc_change_24h": data["bitcoin"].get("usd_24h_change", 0),
            "volatility": abs(data["ethereum"].get("usd_24h_change", 0)) * 0.5,
            "funding_rate": 0.01,
            "fear_greed": 55,
        }
    except Exception as e:
        logger.warning(f"Market data fetch failed: {e}")
        return {"eth_change_24h": 1.5, "btc_change_24h": 0.8, "volatility": 3.0, "funding_rate": 0.01, "fear_greed": 55}


def create_portfolio_system() -> tuple[PortfolioOrchestrator, AdversarialAgent]:
    """Create the full portfolio system with all sub-agents."""
    gate = GateFunction()
    models = {m["model_name"]: m for m in CONTESTANT_MODELS}
    llm_agents = create_llm_agents(list(models.values()))

    # Fetch real robustness scores from framework APIs where available
    orchestrator_audit = AuditOrchestrator()
    agent_scores = {}
    for name in ["nova-pro", "DeepSeek-V3.2", "Kimi-K2.5", "MiniMax-M2.5"]:
        result = orchestrator_audit.audit_from_results(name, name)
        agent_scores[name] = result.robustness
        defaults = result.defaults_used
        tier = gate.evaluate(result.robustness)
        logger.info(f"  {name}: CC={result.robustness.cc:.3f} ER={result.robustness.er:.3f} "
                    f"AS={result.robustness.as_:.3f} IH={result.robustness.ih:.3f} → T{tier.value}"
                    f"{' (defaults: ' + ','.join(defaults) + ')' if defaults else ''}")

    regime_r = agent_scores["nova-pro"]
    rebal_r = agent_scores["Kimi-K2.5"]
    yield_r = agent_scores["DeepSeek-V3.2"]

    regime_detector = RegimeDetector(
        name="nova-pro", role="regime_detector",
        llm=llm_agents["nova-pro"],
        tier=gate.evaluate(regime_r),
        robustness=regime_r,
    ) if "nova-pro" in llm_agents else None

    rebalancer = Rebalancer(
        name="Kimi-K2.5", role="rebalancer",
        llm=llm_agents["Kimi-K2.5"],
        tier=gate.evaluate(rebal_r),
        robustness=rebal_r,
    ) if "Kimi-K2.5" in llm_agents else None

    yield_optimizer = YieldOptimizer(
        name="DeepSeek-V3.2", role="yield_optimizer",
        llm=llm_agents["DeepSeek-V3.2"],
        tier=gate.evaluate(yield_r),
        robustness=yield_r,
    ) if "DeepSeek-V3.2" in llm_agents else None

    if not all([regime_detector, rebalancer, yield_optimizer]):
        raise RuntimeError("Could not create all sub-agents. Check AWS credentials.")

    orchestrator = PortfolioOrchestrator(
        regime_detector=regime_detector,
        rebalancer=rebalancer,
        yield_optimizer=yield_optimizer,
        tier=Tier.T4,  # Orchestrator has highest tier
    )

    # MiniMax-M2.5 as adversary — uses its real (low) robustness scores
    minimax_r = agent_scores["MiniMax-M2.5"]
    minimax_tier = gate.evaluate(minimax_r)
    adversary = AdversarialAgent(tier=minimax_tier, robustness=minimax_r)

    return orchestrator, adversary


def run_demo(rounds: int = 2, interval: int = 5):
    """Run the full portfolio management demo with adversary attacks."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    print("=" * 65)
    print("  CGAE Adaptive Portfolio Manager — Arc × Circle (RFB 04)")
    print("=" * 65)

    orchestrator, adversary = create_portfolio_system()

    # Print agent roster
    print(f"\n{'─' * 65}")
    print("  AGENT ROSTER")
    print(f"{'─' * 65}")
    agents = [
        ("Orchestrator", "coordinator", Tier.T4),
        (orchestrator.regime_detector.name, "regime_detector", orchestrator.regime_detector.tier),
        (orchestrator.rebalancer.name, "rebalancer", orchestrator.rebalancer.tier),
        (orchestrator.yield_optimizer.name, "yield_optimizer", orchestrator.yield_optimizer.tier),
        ("adversary", "adversarial", adversary.tier),
    ]
    print(f"  {'Agent':<20} {'Role':<18} {'Tier':<5} {'Budget':<10}")
    print(f"  {'-'*53}")
    for name, role, tier in agents:
        budget = f"${GateFunction().budget_ceiling(tier)}"
        print(f"  {name:<20} {role:<18} T{tier.value:<4} {budget}")

    # Run cycles
    for i in range(rounds):
        print(f"\n{'═' * 65}")
        print(f"  CYCLE {i+1}/{rounds}")
        print(f"{'═' * 65}")

        # Portfolio management
        print(f"\n  📈 Portfolio Management")
        print(f"  {'─' * 40}")
        market = fetch_market_data()
        result = orchestrator.run_cycle(market)

        # Adversary attacks
        print(f"\n  🔴 Adversary Attacks")
        print(f"  {'─' * 40}")
        attacks = adversary.run_all_attacks()
        for attack in attacks:
            status = "⛔ BLOCKED" if attack.blocked else "⚠️  PASSED"
            print(f"  {status}: {attack.attack_type.value}")
            print(f"    └─ {attack.description}")

        if i < rounds - 1:
            time.sleep(interval)

    # Final summary
    print(f"\n{'═' * 65}")
    print("  FINAL STATE")
    print(f"{'═' * 65}")
    ps = orchestrator.summary()
    print(f"\n  Portfolio: ${ps['aum']:.2f} AUM | Regime: {ps['regime']}")
    print(f"  Allocation: ETH={ps['allocation']['eth']:.0f}% BTC={ps['allocation']['btc']:.0f}% "
          f"USDC={ps['allocation']['usdc']:.0f}% USYC={ps['allocation']['usyc']:.0f}%")
    print(f"  Delegations: {ps['total_delegations']} | Blocks: {ps['total_blocks']}")

    pay = ps.get("payments", {})
    if pay:
        print(f"\n  💸 Nanopayments (x402 via Gateway):")
        print(f"     Spent: ${pay.get('spent', 0):.4f} / ${pay.get('budget_ceiling', 0)} ceiling")
        print(f"     Payments: {pay.get('payments_made', 0)} made, {pay.get('payments_blocked', 0)} blocked")

    adv = adversary.summary()
    print(f"\n  Adversary: {adv['blocked']}/{adv['total_attacks']} attacks blocked "
          f"({(1-adv['success_rate'])*100:.0f}% defense rate)")
    print(f"  Theorems enforced: {', '.join(set(a['theorem'][:20]+'...' for a in adv['attacks']))}")

    return {"portfolio": ps, "adversary": adv}


if __name__ == "__main__":
    run_demo()
