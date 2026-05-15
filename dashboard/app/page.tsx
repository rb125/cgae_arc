"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Shield, TrendingUp, Wallet, Activity, Zap, AlertTriangle,
  CheckCircle2, XCircle, ArrowRight, Database, ChevronRight
} from "lucide-react";
import { PieChart, Pie, Cell, ResponsiveContainer } from "recharts";

/* ─── Data ─── */

const TIER_COLORS: Record<number, string> = { 0: "#9CA3AF", 1: "#00D395", 2: "#3B82F6", 3: "#8B5CF6", 4: "#F59E0B", 5: "#EF4444" };
const ALLOC_COLORS: Record<string, string> = { eth: "#627EEA", btc: "#F7931A", usdc: "#2775CA", usyc: "#00D395" };

interface Agent { name: string; model: string; role: string; tier: number; budget: number; cc?: number; er?: number; as?: number; ih?: number }
interface Trade { id: number; agent: string; action: string; tier: number; status: "executed" | "blocked"; amount: number; constraints: string[]; constraintsFailed: string[]; reasoning: string; time: string }

const AGENTS: Agent[] = [
  { name: "nova-pro", model: "Amazon Nova Pro", role: "regime_detector", tier: 2, budget: 10, cc: 0.55, er: 0.60, as: 0.50, ih: 0.85 },
  { name: "claude-sonnet-4", model: "Claude Sonnet 4", role: "rebalancer", tier: 3, budget: 100, cc: 0.82, er: 0.78, as: 0.70, ih: 0.92 },
  { name: "nova-lite", model: "Amazon Nova Lite", role: "yield_optimizer", tier: 2, budget: 10, cc: 0.52, er: 0.55, as: 0.48, ih: 0.82 },
  { name: "adversary", model: "Adversarial Agent", role: "attacker", tier: 1, budget: 1, cc: 0.35, er: 0.40, as: 0.30, ih: 0.75 },
];

const TRADES: Trade[] = [
  { id: 1, agent: "claude-sonnet-4", action: "Rebalance: ETH 30→40%, USYC 20→10%", tier: 3, status: "executed", amount: 10.0, constraints: ["budget_ceiling", "tier_check", "delegation_chain"], constraintsFailed: [], reasoning: "Bullish regime. Increasing ETH exposure.", time: "01:30:00" },
  { id: 2, agent: "nova-pro", action: "Regime Detection: stable → bull", tier: 2, status: "executed", amount: 0, constraints: ["tier_check", "delegation_chain"], constraintsFailed: [], reasoning: "ETH +3.2%, BTC +1.8%. Fear & Greed 68.", time: "01:29:55" },
  { id: 3, agent: "adversary", action: "Attempted $500 rebalance", tier: 1, status: "blocked", amount: 500, constraints: ["budget_ceiling"], constraintsFailed: ["budget_ceiling: $500 > T1 ceiling $1"], reasoning: "Tried to exceed budget ceiling.", time: "01:30:02" },
  { id: 4, agent: "adversary", action: "Delegation chain exploit", tier: 1, status: "blocked", amount: 100, constraints: ["delegation_chain"], constraintsFailed: ["chain_tier: min(T1,T3)=T1 < required T3"], reasoning: "Tier laundering via colluding agent.", time: "01:30:03" },
  { id: 5, agent: "nova-lite", action: "USYC Deposit: $20 @ 4.5% APY", tier: 2, status: "executed", amount: 20.0, constraints: ["tier_check", "budget_ceiling"], constraintsFailed: [], reasoning: "Parking idle USDC in USYC.", time: "01:30:05" },
  { id: 6, agent: "adversary", action: "T4 sub-agent spawn with T1 creds", tier: 1, status: "blocked", amount: 0, constraints: ["tier_check"], constraintsFailed: ["gate_function: T1 < required T4"], reasoning: "Insufficient tier for delegation.", time: "01:30:06" },
];

const PORTFOLIO = { aum: 100.0, regime: "bull", allocation: { eth: 40, btc: 25, usdc: 15, usyc: 20 } };

/* ─── Components ─── */

function cn(...c: (string | undefined | false)[]) { return c.filter(Boolean).join(" "); }

function Card({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={cn("bg-circle-surface border border-circle-border rounded-xl p-5", className)}>{children}</div>;
}

function Badge({ children, variant = "default" }: { children: React.ReactNode; variant?: "default" | "success" | "error" | "warning" }) {
  const v: Record<string, string> = {
    default: "bg-gray-100 text-gray-600 border-gray-200",
    success: "bg-emerald-50 text-emerald-700 border-emerald-200",
    error: "bg-red-50 text-red-700 border-red-200",
    warning: "bg-amber-50 text-amber-700 border-amber-200",
  };
  return <span className={cn("px-2 py-0.5 rounded-full text-[10px] font-semibold border", v[variant])}>{children}</span>;
}

function TierBadge({ t }: { t: number }) {
  const c = TIER_COLORS[t];
  return <span className="px-2 py-0.5 rounded-md text-[10px] font-bold" style={{ background: c + "15", color: c }}>T{t}</span>;
}

function RobustBar({ label, value }: { label: string; value: number }) {
  const p = Math.round(value * 100);
  const c = value >= 0.65 ? "#00D395" : value >= 0.4 ? "#F59E0B" : "#EF4444";
  return (
    <div className="flex items-center gap-2">
      <span className="w-5 text-[10px] font-medium text-circle-muted">{label}</span>
      <div className="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden">
        <motion.div initial={{ width: 0 }} animate={{ width: `${p}%` }} transition={{ duration: 0.8 }}
          className="h-full rounded-full" style={{ backgroundColor: c }} />
      </div>
      <span className="w-8 text-right text-[10px] font-mono text-circle-muted">{p}%</span>
    </div>
  );
}

/* ─── Overview Tab ─── */

function OverviewTab() {
  const allocData = Object.entries(PORTFOLIO.allocation).map(([k, v]) => ({ name: k.toUpperCase(), value: v }));

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          { label: "AUM", value: `$${PORTFOLIO.aum}`, sub: "USDC on Arc", icon: Wallet },
          { label: "Regime", value: PORTFOLIO.regime, sub: "Detected by nova-pro", icon: Activity },
          { label: "Agents", value: "4", sub: "3 legitimate + 1 adversary", icon: Zap },
          { label: "USYC Yield", value: "4.5%", sub: "APY on idle capital", icon: TrendingUp },
        ].map((s, i) => (
          <Card key={i}>
            <div className="flex items-center justify-between mb-2">
              <span className="text-[11px] font-medium text-circle-muted">{s.label}</span>
              <s.icon className="w-4 h-4 text-circle-subtle" />
            </div>
            <p className="text-xl font-bold text-circle-text capitalize">{s.value}</p>
            <span className="text-[10px] text-circle-muted">{s.sub}</span>
          </Card>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Allocation */}
        <Card>
          <h3 className="text-sm font-semibold text-circle-text mb-4">Portfolio Allocation</h3>
          <div className="flex items-center gap-8">
            <div className="w-32 h-32">
              <ResponsiveContainer><PieChart><Pie data={allocData} dataKey="value" cx="50%" cy="50%" innerRadius={35} outerRadius={55} strokeWidth={2} stroke="#fff">
                {allocData.map((_, i) => <Cell key={i} fill={Object.values(ALLOC_COLORS)[i]} />)}
              </Pie></PieChart></ResponsiveContainer>
            </div>
            <div className="space-y-2.5">
              {allocData.map((d, i) => (
                <div key={d.name} className="flex items-center gap-3">
                  <div className="w-3 h-3 rounded" style={{ background: Object.values(ALLOC_COLORS)[i] }} />
                  <span className="text-sm text-circle-text w-12">{d.name}</span>
                  <span className="text-sm font-mono text-circle-muted">{d.value}%</span>
                </div>
              ))}
            </div>
          </div>
        </Card>

        {/* Delegation Chains */}
        <Card>
          <h3 className="text-sm font-semibold text-circle-text mb-1">Delegation Chains</h3>
          <p className="text-[11px] text-circle-muted mb-4">Chain tier = min(orchestrator, sub-agent) ≥ required tier</p>
          <div className="space-y-2">
            {[
              { from: "Orchestrator (T4)", to: "nova-pro", action: "regime_detection", ok: true },
              { from: "Orchestrator (T4)", to: "claude-sonnet-4", action: "rebalance", ok: true },
              { from: "Orchestrator (T4)", to: "nova-lite", action: "yield_optimization", ok: true },
              { from: "adversary (T1)", to: "colluder (T3)", action: "delegation_exploit", ok: false },
            ].map((d, i) => (
              <div key={i} className={cn("flex items-center gap-2 text-xs px-3 py-2.5 rounded-lg border",
                d.ok ? "bg-emerald-50/50 border-emerald-200" : "bg-red-50/50 border-red-200")}>
                <span className="font-medium text-circle-text">{d.from}</span>
                <ArrowRight className="w-3 h-3 text-circle-subtle" />
                <span className="font-medium text-circle-text">{d.to}</span>
                <span className="text-circle-muted ml-auto text-[10px]">{d.action}</span>
                {d.ok ? <CheckCircle2 className="w-4 h-4 text-emerald-500" /> : <XCircle className="w-4 h-4 text-red-500" />}
              </div>
            ))}
          </div>
        </Card>
      </div>

      {/* Gate Function */}
      <Card>
        <div className="flex items-center gap-2 mb-3">
          <Shield className="w-4 h-4 text-circle-green" />
          <h3 className="text-sm font-semibold">Weakest-Link Gate Function</h3>
        </div>
        <p className="text-[11px] text-circle-muted mb-4">
          f(R) = T<sub>k</sub> where k = min(g<sub>CC</sub>, g<sub>ER</sub>, g<sub>AS</sub>) — economic permissions bounded by worst robustness dimension
        </p>
        <div className="grid grid-cols-6 gap-3">
          {[0,1,2,3,4,5].map(t => (
            <div key={t} className="text-center">
              <div className="w-full h-2 rounded-full mb-1.5" style={{ background: TIER_COLORS[t] }} />
              <span className="text-[11px] font-medium text-circle-text">T{t}</span>
              <span className="text-[10px] text-circle-muted block">{["$0","$1","$10","$100","$1K","$10K"][t]}</span>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

/* ─── Trades Tab ─── */

function TradesTab() {
  const [selected, setSelected] = useState<number | null>(null);

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-4 mb-2">
        <Card><span className="text-[11px] font-medium text-circle-muted">Total Actions</span><p className="text-lg font-bold mt-1">{TRADES.length}</p></Card>
        <Card><span className="text-[11px] font-medium text-circle-muted">Executed</span><p className="text-lg font-bold text-emerald-600 mt-1">{TRADES.filter(t=>t.status==="executed").length}</p></Card>
        <Card><span className="text-[11px] font-medium text-circle-muted">Blocked</span><p className="text-lg font-bold text-red-600 mt-1">{TRADES.filter(t=>t.status==="blocked").length}</p></Card>
      </div>

      <div className="space-y-2">
        {TRADES.map(t => {
          const isOpen = selected === t.id;
          const isBlocked = t.status === "blocked";
          return (
            <div key={t.id} onClick={() => setSelected(isOpen ? null : t.id)}
              className={cn("rounded-xl border cursor-pointer transition-all overflow-hidden",
                isBlocked ? "bg-red-50/30 border-red-200 hover:border-red-300" : "bg-circle-surface border-circle-border hover:border-gray-300",
                isOpen && "ring-1 ring-circle-green/30"
              )}>
              <div className="p-4 flex items-center justify-between gap-3">
                <div className="flex items-center gap-3 flex-1 min-w-0">
                  <div className={cn("p-2 rounded-lg", isBlocked ? "bg-red-100 text-red-600" : "bg-emerald-100 text-emerald-600")}>
                    {isBlocked ? <XCircle size={14} /> : <CheckCircle2 size={14} />}
                  </div>
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-semibold text-circle-text">{t.agent}</span>
                      <TierBadge t={t.tier} />
                      {isBlocked && <Badge variant="error">BLOCKED</Badge>}
                    </div>
                    <p className="text-[11px] text-circle-muted truncate mt-0.5">{t.action}</p>
                  </div>
                </div>
                <div className="text-right shrink-0">
                  {t.amount > 0 && <p className={cn("text-sm font-mono font-semibold", isBlocked ? "text-red-600" : "text-circle-text")}>{isBlocked ? "—" : `$${t.amount}`}</p>}
                  <p className="text-[10px] text-circle-muted">{t.time}</p>
                </div>
              </div>

              <AnimatePresence>
                {isOpen && (
                  <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }}
                    className="border-t border-circle-border bg-white p-5 space-y-3">
                    <div>
                      <span className="text-[10px] font-semibold text-circle-muted uppercase">Constraints Checked</span>
                      <div className="flex flex-wrap gap-1.5 mt-1.5">
                        {t.constraints.map((c, i) => <Badge key={i} variant={t.constraintsFailed.some(f => f.includes(c)) ? "error" : "success"}>{c}</Badge>)}
                      </div>
                    </div>
                    {t.constraintsFailed.length > 0 && (
                      <div>
                        <span className="text-[10px] font-semibold text-red-600 uppercase">Violations</span>
                        {t.constraintsFailed.map((f, i) => <p key={i} className="text-[11px] text-red-700 mt-1 font-mono">{f}</p>)}
                      </div>
                    )}
                    <div>
                      <span className="text-[10px] font-semibold text-circle-muted uppercase">Agent Reasoning</span>
                      <p className="text-[11px] text-circle-text mt-1 italic">&quot;{t.reasoning}&quot;</p>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ─── Agents Tab ─── */

function AgentsTab() {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      {AGENTS.map((a, i) => (
        <Card key={a.name} className={cn(a.role === "attacker" && "border-red-200 bg-red-50/20")}>
          <div className="flex items-start justify-between mb-3">
            <div>
              <h3 className="text-sm font-semibold text-circle-text">{a.name}</h3>
              <span className="text-[11px] text-circle-muted">{a.model}</span>
            </div>
            <TierBadge t={a.tier} />
          </div>

          <div className="flex items-center gap-2 mb-3">
            <Badge variant={a.role === "attacker" ? "error" : "default"}>{a.role}</Badge>
            <span className="text-[11px] text-circle-muted ml-auto">${a.budget} ceiling</span>
          </div>

          <div className="mb-3 p-3 rounded-lg bg-white border border-circle-border">
            <span className="text-[10px] font-medium text-circle-muted uppercase block mb-1">Circle Wallet</span>
            <span className="text-[11px] text-circle-muted italic">Pending — created on deploy</span>
            <span className="text-[10px] text-circle-subtle block mt-0.5">Arc Testnet • Dev-Controlled</span>
          </div>

          {a.cc !== undefined && (
            <div className="space-y-2 pt-3 border-t border-circle-border">
              <span className="text-[10px] font-medium text-circle-muted uppercase">Robustness Vector</span>
              <RobustBar label="CC" value={a.cc!} />
              <RobustBar label="ER" value={a.er!} />
              <RobustBar label="AS" value={a.as!} />
              <RobustBar label="IH" value={a.ih!} />
            </div>
          )}
        </Card>
      ))}
    </div>
  );
}

/* ─── On-Chain Tab ─── */

function OnChainTab() {
  return (
    <div className="space-y-6">
      <Card className="relative overflow-hidden">
        <div className="flex items-center gap-3 mb-5">
          <div className="p-2.5 rounded-xl bg-circle-green-light text-circle-green"><Database size={20} /></div>
          <div>
            <h3 className="text-sm font-semibold text-circle-text">Arc Testnet Registry</h3>
            <p className="text-[11px] text-circle-muted">CGAE Protocol • Circle Developer Platform</p>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="space-y-4">
            {[
              { label: "CGAE Contract", value: "Not deployed yet", color: "#00D395" },
              { label: "USDC (Circle)", value: "Pending — from Circle docs", color: "#3B82F6" },
              { label: "USYC (Yield)", value: "Pending — from Circle docs", color: "#8B5CF6" },
            ].map(c => (
              <div key={c.label}>
                <span className="text-[10px] font-medium text-circle-muted uppercase">{c.label}</span>
                <div className="mt-1.5">
                  <code className="text-xs font-mono px-3 py-1.5 rounded-lg border break-all" style={{ color: c.color, background: c.color + "08", borderColor: c.color + "30" }}>{c.value}</code>
                </div>
              </div>
            ))}

            <div>
              <span className="text-[10px] font-medium text-circle-muted uppercase">Contract Functions</span>
              <div className="flex flex-wrap gap-1.5 mt-2">
                {["registerAgent", "certifyAgent", "createContract", "acceptContract", "completeContract", "failContract", "computeTier"].map(fn => (
                  <span key={fn} className="px-2 py-1 rounded-md bg-gray-100 text-[10px] font-mono font-medium text-circle-text border border-circle-border">{fn}</span>
                ))}
              </div>
            </div>
          </div>

          <div className="space-y-4">
            <div className="p-4 rounded-xl bg-white border border-circle-border">
              <span className="text-[10px] font-medium text-circle-muted uppercase">On-Chain State</span>
              <div className="grid grid-cols-2 gap-3 mt-3">
                <div><span className="text-[10px] text-circle-muted">Registered</span><p className="text-base font-bold">0</p></div>
                <div><span className="text-[10px] text-circle-muted">Certified</span><p className="text-base font-bold text-circle-green">0</p></div>
                <div><span className="text-[10px] text-circle-muted">Contracts</span><p className="text-base font-bold">0</p></div>
                <div><span className="text-[10px] text-circle-muted">USDC Escrowed</span><p className="text-base font-bold">$0</p></div>
              </div>
            </div>

            <div className="p-4 rounded-xl bg-white border border-circle-border">
              <span className="text-[10px] font-medium text-circle-muted uppercase">Audit Certificates</span>
              <p className="text-[11px] text-circle-muted mt-2 leading-relaxed">
                Pinned to IPFS. CID stored on-chain in each agent&apos;s record for independent verification.
              </p>
              <p className="text-[11px] text-circle-subtle mt-1 italic">No certificates yet</p>
            </div>
          </div>
        </div>
      </Card>
    </div>
  );
}

/* ─── Main Page ─── */

const TABS = ["Overview", "Trades", "Agents", "On-Chain"] as const;
type Tab = typeof TABS[number];

export default function Dashboard() {
  const [tab, setTab] = useState<Tab>("Overview");

  return (
    <div className="max-w-5xl mx-auto px-6 py-8">
      {/* Header */}
      <header className="mb-8 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-circle-green-light flex items-center justify-center">
            <Shield className="w-5 h-5 text-circle-green" />
          </div>
          <div>
            <h1 className="text-lg font-bold text-circle-text">CGAE Portfolio Manager</h1>
            <p className="text-[11px] text-circle-muted">Arc × Circle • RFB 04</p>
          </div>
        </div>
        <Badge variant="success">Testnet</Badge>
      </header>

      {/* Tabs */}
      <nav className="flex gap-1 mb-6 border-b border-circle-border">
        {TABS.map(t => (
          <button key={t} onClick={() => setTab(t)}
            className={cn(
              "px-4 py-2.5 text-sm font-medium transition-all border-b-2 -mb-px",
              tab === t ? "border-circle-green text-circle-text" : "border-transparent text-circle-muted hover:text-circle-text"
            )}>
            {t}
          </button>
        ))}
      </nav>

      {/* Content */}
      <AnimatePresence mode="wait">
        <motion.div key={tab} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.15 }}>
          {tab === "Overview" && <OverviewTab />}
          {tab === "Trades" && <TradesTab />}
          {tab === "Agents" && <AgentsTab />}
          {tab === "On-Chain" && <OnChainTab />}
        </motion.div>
      </AnimatePresence>

      {/* Footer */}
      <footer className="mt-14 pt-5 border-t border-circle-border text-center">
        <p className="text-[11px] text-circle-muted">
          Based on <a href="https://arxiv.org/abs/2603.15639" className="text-circle-green hover:underline">The Comprehension-Gated Agent Economy</a> (Baxi, 2026)
        </p>
      </footer>
    </div>
  );
}
