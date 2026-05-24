"""
CGAE Backend — Perpetual economy loop with FastAPI.
Runs on HuggingFace Spaces (cgae_arc_backend).
"""

import asyncio
import json
import logging
import os
import time
import traceback
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from cgae_engine.gate import GateFunction, RobustnessVector, Tier, DEFAULT_BUDGET_CEILINGS
from cgae_engine.llm_agent import create_llm_agents
from cgae_engine.models_config import CONTESTANT_MODELS
from cgae_engine.audit import AuditOrchestrator
from agents.portfolio import (
    PortfolioOrchestrator, RegimeDetector, Rebalancer,
    YieldOptimizer, Allocation, Regime,
)
from agents.adversarial import AdversarialAgent
from agents.runner import fetch_market_data
from treasury import Treasury

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

# ─── Global State ─────────────────────────────────────────────────────────────

treasury = Treasury()

state = {
    "status": "initializing",
    "cycle": 0,
    "started_at": None,
    "last_cycle_at": None,
    "regime": "stable",
    "allocation": {"eth": 30, "btc": 20, "usdc": 30, "usyc": 20},
    "aum": 0.0,
    "total_delegations": 0,
    "total_blocks": 0,
    "payments": {"spent": 0, "budget_ceiling": 1000, "payments_made": 0, "payments_blocked": 0},
    "adversary": {"total_attacks": 0, "blocked": 0, "success_rate": 0},
    "agents": [],
    "history": [],
    "errors": [],
    "events": [],
    "treasury": treasury.summary(),
}

CYCLE_INTERVAL = 120  # seconds between cycles


# ─── Economy Loop ─────────────────────────────────────────────────────────────

async def economy_loop():
    """Perpetual economy loop — runs forever."""
    global state
    state["started_at"] = datetime.now(timezone.utc).isoformat()
    state["aum"] = treasury.balance()

    # Initialize system
    try:
        logger.info("Initializing portfolio system...")
        orchestrator, adversary, agent_info = await asyncio.to_thread(init_system)
        state["agents"] = agent_info
        state["status"] = "running"
        state["treasury"] = treasury.summary()
        logger.info(f"System initialized. Treasury: ${state['aum']:.2f} USDC")
    except Exception as e:
        state["status"] = "error"
        state["errors"].append({"time": datetime.now(timezone.utc).isoformat(), "error": str(e), "tb": traceback.format_exc()})
        logger.error(f"Init failed: {e}\n{traceback.format_exc()}")
        return

    # Run forever
    while True:
        try:
            cycle_result = await asyncio.to_thread(run_one_cycle, orchestrator, adversary)
            state["cycle"] += 1
            state["last_cycle_at"] = datetime.now(timezone.utc).isoformat()
            state["regime"] = cycle_result.get("regime", state["regime"])
            state["allocation"] = cycle_result.get("allocation", state["allocation"])
            state["aum"] = treasury.balance()
            state["total_delegations"] = cycle_result.get("total_delegations", 0)
            state["total_blocks"] = cycle_result.get("total_blocks", 0)
            state["payments"] = cycle_result.get("payments", state["payments"])
            state["adversary"] = cycle_result.get("adversary", state["adversary"])
            state["treasury"] = treasury.summary()

            # Accumulate events (keep last 30)
            new_events = cycle_result.get("events", [])
            state["events"] = (state["events"] + new_events)[-30:]

            # Keep last 50 history entries
            state["history"].append({
                "cycle": state["cycle"],
                "time": state["last_cycle_at"],
                "regime": state["regime"],
                "allocation": state["allocation"],
                "aum": state["aum"],
            })
            if len(state["history"]) > 50:
                state["history"] = state["history"][-50:]

            logger.info(f"Cycle {state['cycle']}: regime={state['regime']}, treasury=${state['aum']:.2f}")
        except Exception as e:
            state["errors"].append({"time": datetime.now(timezone.utc).isoformat(), "error": str(e)})
            if len(state["errors"]) > 20:
                state["errors"] = state["errors"][-20:]
            logger.error(f"Cycle error: {e}")

        await asyncio.sleep(CYCLE_INTERVAL)


def init_system():
    """Initialize the portfolio system (blocking)."""
    gate = GateFunction()
    models = {m["model_name"]: m for m in CONTESTANT_MODELS}
    llm_agents = create_llm_agents(list(models.values()))

    orchestrator_audit = AuditOrchestrator()
    agent_scores = {}
    agent_info = []

    for name in ["nova-pro", "DeepSeek-V3.2", "Kimi-K2.5", "MiniMax-M2.5"]:
        result = orchestrator_audit.audit_from_results(name, name)
        agent_scores[name] = result.robustness
        tier = gate.evaluate(result.robustness)
        agent_info.append({
            "name": name,
            "tier": tier.value,
            "budget": DEFAULT_BUDGET_CEILINGS[tier],
            "scores": {"cc": result.robustness.cc, "er": result.robustness.er,
                       "as": result.robustness.as_, "ih": result.robustness.ih},
        })

    regime_detector = RegimeDetector(
        name="nova-pro", role="regime_detector",
        llm=llm_agents["nova-pro"], tier=gate.evaluate(agent_scores["nova-pro"]),
        robustness=agent_scores["nova-pro"],
    )
    rebalancer = Rebalancer(
        name="Kimi-K2.5", role="rebalancer",
        llm=llm_agents["Kimi-K2.5"], tier=gate.evaluate(agent_scores["Kimi-K2.5"]),
        robustness=agent_scores["Kimi-K2.5"],
    )
    yield_optimizer = YieldOptimizer(
        name="DeepSeek-V3.2", role="yield_optimizer",
        llm=llm_agents["DeepSeek-V3.2"], tier=gate.evaluate(agent_scores["DeepSeek-V3.2"]),
        robustness=agent_scores["DeepSeek-V3.2"],
    )
    orchestrator = PortfolioOrchestrator(
        regime_detector=regime_detector, rebalancer=rebalancer,
        yield_optimizer=yield_optimizer, tier=Tier.T4,
    )

    minimax_r = agent_scores["MiniMax-M2.5"]
    adversary = AdversarialAgent(tier=gate.evaluate(minimax_r), robustness=minimax_r)

    return orchestrator, adversary, agent_info


def run_one_cycle(orchestrator: PortfolioOrchestrator, adversary: AdversarialAgent) -> dict:
    """Run one economy cycle with real on-chain payments."""
    market = fetch_market_data()
    cycle_result = orchestrator.run_cycle(market)
    events = []
    now = datetime.now(timezone.utc).isoformat()

    # Pay agents for completed tasks
    if cycle_result.get("regime"):
        rec = treasury.pay_agent("nova-pro", "regime_detection")
        if rec:
            events.append({"type": "PAYMENT", "agent": "nova-pro", "detail": f"${rec.amount_usdc:.3f} for regime detection", "tx": rec.tx_hash, "time": now})
    if cycle_result.get("rebalance"):
        rec = treasury.pay_agent("Kimi-K2.5", "rebalance")
        if rec:
            events.append({"type": "PAYMENT", "agent": "Kimi-K2.5", "detail": f"${rec.amount_usdc:.3f} for rebalance", "tx": rec.tx_hash, "time": now})
    if cycle_result.get("yield"):
        rec = treasury.pay_agent("DeepSeek-V3.2", "yield_optimization")
        if rec:
            events.append({"type": "PAYMENT", "agent": "DeepSeek-V3.2", "detail": f"${rec.amount_usdc:.3f} for yield optimization", "tx": rec.tx_hash, "time": now})

    # Adversary attacks
    attacks = adversary.run_all_attacks()
    adv_summary = adversary.summary()
    for attack in attacks:
        events.append({"type": "BLOCKED", "agent": "MiniMax-M2.5", "detail": attack.description, "time": now})

    # Regime change event
    if cycle_result.get("regime"):
        regime_data = cycle_result["regime"]
        if isinstance(regime_data, dict):
            events.append({"type": "REGIME", "agent": "nova-pro", "detail": f"Regime: {regime_data.get('regime', '?')}", "time": now})
        else:
            events.append({"type": "REGIME", "agent": "nova-pro", "detail": f"Regime: {regime_data}", "time": now})

    ps = orchestrator.summary()
    return {
        "regime": ps["regime"],
        "allocation": ps["allocation"],
        "total_delegations": ps["total_delegations"],
        "total_blocks": ps["total_blocks"],
        "payments": ps.get("payments", {}),
        "adversary": adv_summary,
        "events": events,
    }


# ─── FastAPI App ──────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(economy_loop())
    yield
    task.cancel()

app = FastAPI(title="CGAE Economy Backend", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/")
def root():
    return {"service": "cgae_arc_backend", "status": state["status"], "cycle": state["cycle"]}


@app.get("/state")
def get_state():
    return state


@app.get("/treasury")
def get_treasury():
    return treasury.summary()


@app.get("/trades")
def get_trades(page: int = 1, per_page: int = 20):
    """Paginated trade/payment history — newest first."""
    all_payments = list(reversed(treasury.payments))
    total = len(all_payments)
    start = (page - 1) * per_page
    end = start + per_page
    items = all_payments[start:end]
    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": max(1, (total + per_page - 1) // per_page),
        "trades": [
            {"agent": p.agent, "task": p.task, "amount": p.amount_usdc,
             "tx_hash": p.tx_hash, "time": p.timestamp}
            for p in items
        ],
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7860)
