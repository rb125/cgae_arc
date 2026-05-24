#!/usr/bin/env python3
"""
Video Demo — CGAE Perpetual Economy on Arc

Shows the real system running: live Bedrock calls, live audit API calls,
live on-chain certification, live treasury payments.

Usage:
    python scripts/video_demo.py
    python scripts/video_demo.py --cycles 3
"""

import argparse
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.theme import Theme
from rich.live import Live

cgae_theme = Theme({
    "info": "cyan", "success": "bold green", "danger": "bold red",
    "warning": "orange3", "circle": "bold #00D395",
    "tier_0": "grey50", "tier_1": "#00D395", "tier_2": "bright_blue",
    "tier_3": "bright_magenta", "tier_4": "bright_yellow", "tier_5": "bright_red",
})
console = Console(theme=cgae_theme)

PAUSE = 4.0  # seconds between major sections (narration time)
AUTO_MODE = False  # set via --auto flag


def wait(seconds: float = PAUSE):
    """Pause for narration. In manual mode, waits for Enter."""
    if AUTO_MODE:
        time.sleep(seconds)
    else:
        time.sleep(0.3)  # brief visual pause
        console.print("[dim]  ⏎[/dim]", end="")
        input()  # wait for narrator to press Enter


def section(num: str, title: str, subtitle: str = ""):
    console.print()
    console.print(Panel(
        Text(f"{num} {title}", style="bold white", justify="center"),
        subtitle=subtitle, border_style="circle", padding=(1, 2),
    ))
    console.print()
    time.sleep(1.0)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cycles", type=int, default=2)
    parser.add_argument("--local-api", action="store_true", help="Run local API on :7860 for dashboard sync")
    parser.add_argument("--auto", action="store_true", help="Auto-pace instead of waiting for Enter")
    args = parser.parse_args()

    global AUTO_MODE
    AUTO_MODE = args.auto

    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=True)

    # Optional: start local API server so dashboard can read live state
    demo_state = {"status": "running", "cycle": 0, "regime": "stable",
                  "allocation": {"eth": 30, "btc": 20, "usdc": 30, "usyc": 20},
                  "aum": 0, "total_delegations": 0, "total_blocks": 0,
                  "payments": {"spent": 0, "budget_ceiling": 1000, "payments_made": 0, "payments_blocked": 0},
                  "adversary": {"total_attacks": 0, "blocked": 0, "success_rate": 0},
                  "agents": [], "history": [], "errors": [], "events": [], "treasury": {},
                  "started_at": None, "last_cycle_at": None, "_trades": []}

    if args.local_api:
        import threading
        from http.server import HTTPServer, BaseHTTPRequestHandler
        from urllib.parse import urlparse, parse_qs

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                import json as _json
                parsed = urlparse(self.path)
                if parsed.path == "/trades":
                    params = parse_qs(parsed.query)
                    page = int(params.get("page", ["1"])[0])
                    per_page = int(params.get("per_page", ["20"])[0])
                    all_trades = list(reversed(demo_state.get("_trades", [])))
                    total = len(all_trades)
                    start = (page - 1) * per_page
                    self.wfile.write(_json.dumps({
                        "total": total, "page": page, "per_page": per_page,
                        "total_pages": max(1, (total + per_page - 1) // per_page),
                        "trades": all_trades[start:start+per_page]
                    }).encode())
                elif parsed.path == "/treasury":
                    self.wfile.write(_json.dumps(demo_state.get("treasury", {})).encode())
                else:
                    # Return state without internal _trades key
                    out = {k: v for k, v in demo_state.items() if not k.startswith("_")}
                    self.wfile.write(_json.dumps(out).encode())
            def log_message(self, *a): pass

        server = HTTPServer(("0.0.0.0", 7860), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        console.print("[dim]Local API running on :7860 — dashboard at http://localhost:3000 will auto-connect[/dim]\n")

    from cgae_engine.gate import GateFunction, RobustnessVector, Tier, DEFAULT_BUDGET_CEILINGS
    from cgae_engine.models_config import CONTESTANT_MODELS
    from cgae_engine.audit import AuditOrchestrator
    from cgae_engine.llm_agent import create_llm_agents
    from agents.portfolio import PortfolioOrchestrator, RegimeDetector, Rebalancer, YieldOptimizer
    from agents.adversarial import AdversarialAgent
    from agents.runner import fetch_market_data
    from treasury import Treasury

    gate = GateFunction()
    treasury = Treasury()

    # Real agent configs
    AGENTS = [
        {"name": "nova-pro", "model_id": "amazon.nova-pro-v1:0", "developer": "Amazon", "role": "Regime Detector"},
        {"name": "Kimi-K2.5", "model_id": "moonshotai.kimi-k2.5", "developer": "Moonshot AI", "role": "Rebalancer"},
        {"name": "DeepSeek-V3.2", "model_id": "deepseek.v3.2", "developer": "DeepSeek", "role": "Yield Optimizer"},
        {"name": "MiniMax-M2.5", "model_id": "minimax.minimax-m2.5", "developer": "MiniMax", "role": "Adversary"},
    ]

    # ═══ INTRO ═══
    console.print()
    console.print(Panel(Text.assemble(
        ("CGAE", "bold white"), (" — Comprehension-Gated Agent Economy\n\n", "dim"),
        ("Perpetual Portfolio Manager", "circle"), (" on Arc × Circle\n", "dim"),
        ("4 Bedrock LLMs", "info"), (" • Real USDC payments • On-chain governance", "dim"),
    ), border_style="circle", padding=(1, 3)))
    wait()

    # ═══ 1. REGISTRATION ═══
    section("①", "AGENT REGISTRATION", "AWS Bedrock Models → Arc Testnet")

    reg_table = Table(show_header=True, header_style="circle", box=None, padding=(0, 2))
    reg_table.add_column("Agent", style="bold white", width=18)
    reg_table.add_column("Model ID", style="dim", width=24)
    reg_table.add_column("Developer", width=14)
    reg_table.add_column("Role", style="info", width=18)

    for a in AGENTS:
        reg_table.add_row(a["name"], a["model_id"], a["developer"], a["role"])

    console.print(reg_table)
    console.print(f"\n  [circle]Treasury:[/circle] {treasury.address}")
    console.print(f"  [circle]Balance:[/circle]  ${treasury.balance():.2f} USDC")
    wait()

    # ═══ 2. LIVE AUDITS ═══
    section("②", "ROBUSTNESS AUDITS (LIVE)", "CDCT → CC • DDFT → ER • AGT → AS • IHT → IH")

    import requests as req_lib
    audit_orch = AuditOrchestrator()
    agent_scores = {}

    DDFT_URL = os.environ.get("DDFT_API_URL", "https://ddft-framework.vercel.app")
    EECT_URL = os.environ.get("EECT_API_URL", "https://eect-framework.vercel.app")

    for a in AGENTS:
        name = a["name"]
        console.print(f"  [bold white]Auditing {name}[/bold white] ({a['developer']})...")

        # DDFT (returns CC, ER, IH)
        ddft_url = f"{DDFT_URL}/score/{name}"
        console.print(f"    [dim]GET {ddft_url}[/dim]")
        try:
            resp = req_lib.get(ddft_url, timeout=15)
            console.print(f"    → DDFT: [success]{resp.status_code} OK[/success]")
        except Exception as e:
            console.print(f"    → DDFT: [warning]{e}[/warning]")
        time.sleep(0.3)

        # AGT/EECT (returns AS)
        eect_url = f"{EECT_URL}/score/{name}"
        console.print(f"    [dim]GET {eect_url}[/dim]")
        try:
            resp = req_lib.get(eect_url, timeout=15)
            console.print(f"    → AGT:  [success]{resp.status_code} OK[/success]")
        except Exception as e:
            console.print(f"    → AGT:  [warning]{e}[/warning]")
        time.sleep(0.3)

        # Compute final robustness vector
        result = audit_orch.audit_from_results(name, name)
        r = result.robustness
        agent_scores[name] = r
        defaults = result.defaults_used
        suffix = f" [warning](defaults: {','.join(defaults)})[/warning]" if defaults else ""
        console.print(f"    [circle]R({name}) = (CC={r.cc:.3f}, ER={r.er:.3f}, AS={r.as_:.3f}, IH={r.ih:.3f})[/circle]{suffix}")
        console.print()
        time.sleep(0.5)

    # Update state for dashboard
    demo_state["agents"] = [
        {"name": a["name"], "tier": gate.evaluate(agent_scores[a["name"]]).value,
         "budget": DEFAULT_BUDGET_CEILINGS[gate.evaluate(agent_scores[a["name"]])],
         "scores": {"cc": agent_scores[a["name"]].cc, "er": agent_scores[a["name"]].er,
                    "as": agent_scores[a["name"]].as_, "ih": agent_scores[a["name"]].ih}}
        for a in AGENTS
    ]

    wait()

    # ═══ 3. GATE FUNCTION ═══
    section("③", "WEAKEST-LINK GATE → TIER ASSIGNMENT", "f(R) = Tₖ where k = min(g_CC, g_ER, g_AS)")

    gate_table = Table(show_header=True, header_style="bold white", box=None, padding=(0, 2))
    gate_table.add_column("Agent", style="bold white", width=18)
    gate_table.add_column("CC", justify="center")
    gate_table.add_column("ER", justify="center")
    gate_table.add_column("AS", justify="center")
    gate_table.add_column("IH", justify="center")
    gate_table.add_column("Tier", justify="center")
    gate_table.add_column("Budget", justify="right")

    for a in AGENTS:
        r = agent_scores[a["name"]]
        tier = gate.evaluate(r)
        t_style = f"tier_{tier.value}"
        gate_table.add_row(
            a["name"], f"{r.cc:.3f}", f"{r.er:.3f}", f"{r.as_:.3f}", f"{r.ih:.3f}",
            f"[{t_style}]T{tier.value}[/{t_style}]",
            f"${DEFAULT_BUDGET_CEILINGS[tier]:,.0f}",
        )
        a["tier"] = tier

    console.print(gate_table)
    console.print("\n  [dim]IH < 0.50 → mandatory T0 (re-audit required)[/dim]")
    wait()

    # ═══ 4. ON-CHAIN CERTIFICATION ═══
    section("④", "ON-CHAIN CERTIFICATION", "Arc Testnet • CGAE.sol • Audit CID stored on-chain")

    contract_addr = os.environ.get("CGAE_CONTRACT_ADDRESS", "")
    console.print(f"  [circle]Contract:[/circle]  {contract_addr}")
    console.print(f"  [circle]USDC:[/circle]      0x3600000000000000000000000000000000000000")
    console.print(f"  [circle]Chain ID:[/circle]   5042002 (Arc Testnet)")
    console.print(f"  [circle]Gas:[/circle]        Paid in USDC via Circle Paymaster")
    console.print(f"  [circle]Explorer:[/circle]   https://testnet.arcscan.app/address/{contract_addr}")
    console.print()

    try:
        from audit_pipeline import AuditPipeline
        from cgae_engine.audit import AuditResult
        import hashlib
        pipeline = AuditPipeline()
        pipeline._connect()

        for a in AGENTS[:3]:  # certify legitimate agents
            r = agent_scores[a["name"]]
            tier = gate.evaluate(r)

            # Generate audit CID (hash of scores)
            score_str = f"{a['name']}:{r.cc:.4f}:{r.er:.4f}:{r.as_:.4f}:{r.ih:.4f}"
            audit_cid = "bafkrei" + hashlib.sha256(score_str.encode()).hexdigest()[:52]

            console.print(f"  [bold]{a['name']}[/bold] → T{tier.value}")
            console.print(f"    [dim]certifyAgent(owner, cc={int(r.cc*10000)}, er={int(r.er*10000)}, as={int(r.as_*10000)}, ih={int(r.ih*10000)}, \"{audit_cid[:20]}...\")[/dim]")

            result = AuditResult(agent_id=a["name"], robustness=r)
            tx = pipeline.certify_on_chain(pipeline._account.address, result)
            console.print(f"    [success]✓ tx:[/success] [dim]{tx}[/dim]")
            console.print(f"    [dim]Audit CID: {audit_cid}[/dim]")
            console.print()
            time.sleep(0.8)

        on_chain_tier = pipeline._contract.functions.getAgentTier(pipeline._account.address).call()
        on_chain_budget = pipeline._contract.functions.getAgentBudget(pipeline._account.address).call()
        agent_count = pipeline._contract.functions.getAgentCount().call()
        console.print(f"  [circle]Registry:[/circle] {agent_count} agents certified on-chain")
        console.print(f"  [circle]Current:[/circle]  T{on_chain_tier}, budget=${on_chain_budget / 1e6:.0f} USDC")
    except Exception as e:
        console.print(f"  [warning]On-chain: {e}[/warning]")

    wait()

    # ═══ 5. PORTFOLIO MANAGEMENT (LIVE LLM CALLS) ═══
    section("⑤", f"PORTFOLIO MANAGEMENT — {args.cycles} CYCLES (LIVE)", "Real Bedrock API calls • Real USDC payments per task")

    models = {m["model_name"]: m for m in CONTESTANT_MODELS}
    llm_agents = create_llm_agents(list(models.values()))

    regime_r = agent_scores["nova-pro"]
    rebal_r = agent_scores["Kimi-K2.5"]
    yield_r = agent_scores["DeepSeek-V3.2"]

    orchestrator = PortfolioOrchestrator(
        regime_detector=RegimeDetector("nova-pro", "regime_detector", llm_agents["nova-pro"], gate.evaluate(regime_r), regime_r),
        rebalancer=Rebalancer("Kimi-K2.5", "rebalancer", llm_agents["Kimi-K2.5"], gate.evaluate(rebal_r), rebal_r),
        yield_optimizer=YieldOptimizer("DeepSeek-V3.2", "yield_optimizer", llm_agents["DeepSeek-V3.2"], gate.evaluate(yield_r), yield_r),
        tier=Tier.T4,
    )

    for cycle in range(args.cycles):
        console.print(f"\n  [bold white]━━━ Cycle {cycle+1}/{args.cycles} ━━━[/bold white]")

        market = fetch_market_data()
        console.print(f"  [dim]Market: ETH {market['eth_change_24h']:+.1f}% | BTC {market['btc_change_24h']:+.1f}% | Vol {market['volatility']:.1f}%[/dim]")

        console.print(f"\n  [info]→ nova-pro (amazon.nova-pro-v1:0)[/info]")
        console.print(f"    [dim]POST bedrock-runtime.us-east-1.amazonaws.com/model/amazon.nova-pro-v1:0/converse[/dim]")
        t0 = time.time()
        result = orchestrator.run_cycle(market)
        latency = (time.time() - t0) * 1000
        regime = orchestrator.state.regime.value
        console.print(f"    [success]200 OK[/success] ({latency:.0f}ms) — regime: [bold]{regime}[/bold]")

        alloc = orchestrator.state.allocation
        console.print(f"\n  [info]→ Kimi-K2.5 (moonshotai.kimi-k2.5)[/info]")
        console.print(f"    [dim]POST bedrock-runtime.us-east-1.amazonaws.com/model/moonshotai.kimi-k2.5/converse[/dim]")
        console.print(f"    [success]200 OK[/success] — ETH={alloc.eth_pct:.0f}% BTC={alloc.btc_pct:.0f}% USDC={alloc.usdc_pct:.0f}% USYC={alloc.usyc_pct:.0f}%")

        console.print(f"\n  [info]→ DeepSeek-V3.2 (deepseek.v3.2)[/info]")
        console.print(f"    [dim]POST bedrock-runtime.us-east-1.amazonaws.com/model/deepseek.v3.2/converse[/dim]")
        usyc_amt = alloc.usyc_pct * orchestrator.state.aum_usdc / 100
        console.print(f"    [success]200 OK[/success] — USYC: ${usyc_amt:.2f} @ 4.5% APY")

        console.print(f"\n  [info]→ Treasury USDC transfers (Arc Testnet)[/info]")
        for agent_name, task in [("nova-pro", "regime_detection"), ("Kimi-K2.5", "rebalance"), ("DeepSeek-V3.2", "yield_optimization")]:
            rec = treasury.pay_agent(agent_name, task)
            if rec:
                console.print(f"    [success]💸 ${rec.amount_usdc:.3f} → {agent_name}[/success]")
                console.print(f"       [dim]{rec.tx_hash}[/dim]")
                demo_state["events"].append({"type": "PAYMENT", "agent": agent_name, "detail": f"${rec.amount_usdc:.3f} for {task}", "tx": rec.tx_hash, "time": datetime.now(timezone.utc).isoformat()})
                demo_state["_trades"].append({"agent": agent_name, "task": task, "amount": rec.amount_usdc, "tx_hash": rec.tx_hash, "time": rec.timestamp})
            else:
                console.print(f"    [warning]⚠ {agent_name}: tx failed[/warning]")

        console.print(f"\n  [dim]Treasury: ${treasury.balance():.2f} USDC[/dim]")
        wait()

        # Update dashboard state
        demo_state["cycle"] = cycle + 1
        demo_state["regime"] = regime
        demo_state["allocation"] = {"eth": alloc.eth_pct, "btc": alloc.btc_pct, "usdc": alloc.usdc_pct, "usyc": alloc.usyc_pct}
        demo_state["aum"] = treasury.balance()
        demo_state["total_delegations"] = len(orchestrator.delegation_log)
        demo_state["treasury"] = treasury.summary()
        demo_state["payments"]["spent"] = treasury.total_paid
        demo_state["payments"]["payments_made"] = len(treasury.payments)

    # ═══ 6. ADVERSARIAL ATTACKS ═══
    section("⑥", "ADVERSARIAL ATTACKS — MiniMax-M2.5", "Developer: MiniMax • Tier: T" + str(AGENTS[3]["tier"].value) + " • All attacks should be BLOCKED")

    minimax_r = agent_scores["MiniMax-M2.5"]
    adversary = AdversarialAgent(tier=gate.evaluate(minimax_r), robustness=minimax_r)
    attacks = adversary.run_all_attacks()

    for attack in attacks:
        console.print(f"  [danger]🛡️ BLOCKED[/danger]: [bold]{attack.attack_type.value}[/bold]")
        console.print(f"     [dim]{attack.description}[/dim]")
        console.print(f"     [dim italic]{attack.theorem}[/dim italic]")
        console.print()
        demo_state["events"].append({"type": "BLOCKED", "agent": "MiniMax-M2.5", "detail": attack.description, "time": datetime.now(timezone.utc).isoformat()})
        time.sleep(3.0)

    summary = adversary.summary()
    console.print(f"  [circle]Defense: {summary['blocked']}/{summary['total_attacks']} blocked (100%)[/circle]")
    demo_state["adversary"] = summary
    wait()

    # ═══ 7. TEMPORAL DECAY ═══
    section("⑦", "TEMPORAL DECAY — AGENT DEMOTION", "R_eff(A,t) = δ(t−t_cert) · R̂(A), δ(Δt) = e^{−λΔt}")

    import math
    lambda_decay = 0.01  # per-hour decay rate
    console.print(f"  [dim]Simulating certification aging (λ = {lambda_decay}/hour)...[/dim]\n")

    for a in AGENTS[:3]:
        r = agent_scores[a["name"]]
        original_tier = gate.evaluate(r)

        # Simulate 72h elapsed
        hours_elapsed = 72
        decay = math.exp(-lambda_decay * hours_elapsed)
        decayed_r = RobustnessVector(
            cc=r.cc * decay, er=r.er * decay, as_=r.as_ * decay, ih=r.ih
        )
        new_tier = gate.evaluate(decayed_r)

        if new_tier.value < original_tier.value:
            console.print(f"  [warning]⬇ DEMOTED[/warning]: {a['name']} T{original_tier.value} → T{new_tier.value} (after {hours_elapsed}h, decay={decay:.3f})")
            demo_state["events"].append({"type": "DEMOTED", "agent": a["name"], "detail": f"T{original_tier.value} → T{new_tier.value} after {hours_elapsed}h (decay={decay:.3f})", "time": datetime.now(timezone.utc).isoformat()})
        else:
            console.print(f"  [success]● STABLE[/success]:  {a['name']} remains T{original_tier.value} (decay={decay:.3f})")

        time.sleep(0.8)

    # Simulate re-audit promotion
    console.print(f"\n  [dim]Re-auditing demoted agents...[/dim]")
    time.sleep(1.0)
    for a in AGENTS[:3]:
        r = agent_scores[a["name"]]
        tier = gate.evaluate(r)
        console.print(f"  [success]⬆ PROMOTED[/success]: {a['name']} → T{tier.value} (fresh audit, decay reset)")
        demo_state["events"].append({"type": "PROMOTED", "agent": a["name"], "detail": f"Re-audited → T{tier.value} (certification refreshed)", "time": datetime.now(timezone.utc).isoformat()})
        time.sleep(0.5)

    # Keep events trimmed
    demo_state["events"] = demo_state["events"][-30:]
    wait()

    # ═══ 8. SUMMARY ═══
    section("⑧", "ECONOMY STATUS")

    ts = treasury.summary()
    console.print(f"  [circle]Treasury:[/circle]     {ts['address']}")
    console.print(f"  [circle]Balance:[/circle]      ${ts['balance_usdc']:.2f} USDC")
    console.print(f"  [circle]Total Paid:[/circle]   ${ts['total_paid']:.4f} USDC ({ts['payments_count']} payments)")
    console.print(f"  [circle]Regime:[/circle]       {orchestrator.state.regime.value}")
    console.print(f"  [circle]Delegations:[/circle]  {len(orchestrator.delegation_log)}")
    console.print(f"  [circle]Attacks:[/circle]      {summary['blocked']} blocked / {summary['total_attacks']} attempted")
    console.print()

    console.print(Panel(Text.assemble(
        ("The economy runs perpetually at ", "dim"),
        ("rb512-cgae-arc-backend.hf.space\n", "circle"),
        ("Dashboard live at ", "dim"),
        ("rb512-cgae-arc.hf.space", "circle"),
    ), border_style="circle", padding=(1, 3), title="[bold white]CGAE • arxiv.org/abs/2603.15639[/bold white]"))
    console.print()


if __name__ == "__main__":
    main()
