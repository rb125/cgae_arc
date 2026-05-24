"use client";

import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Shield, TrendingUp, Wallet, Activity, Zap, AlertTriangle,
  CheckCircle2, XCircle, ArrowRight, Database, RefreshCw
} from "lucide-react";
import { PieChart, Pie, Cell, ResponsiveContainer } from "recharts";

const API = typeof window !== "undefined" && window.location.hostname === "localhost"
  ? "http://localhost:7860"
  : "https://rb512-cgae-arc-backend.hf.space";

const TIER_COLORS: Record<number, string> = { 0: "#9CA3AF", 1: "#00D395", 2: "#0052FF", 3: "#8B5CF6", 4: "#F59E0B", 5: "#EF4444" };
const ALLOC_COLORS: Record<string, string> = { eth: "#627EEA", btc: "#F7931A", usdc: "#0052FF", usyc: "#00D395" };

interface BackendState {
  status: string;
  cycle: number;
  started_at: string | null;
  last_cycle_at: string | null;
  regime: string;
  allocation: { eth: number; btc: number; usdc: number; usyc: number };
  aum: number;
  total_delegations: number;
  total_blocks: number;
  payments: { spent: number; budget_ceiling: number; payments_made: number; payments_blocked: number };
  adversary: { total_attacks: number; blocked: number; success_rate: number };
  agents: { name: string; tier: number; budget: number; scores: { cc: number; er: number; as: number; ih: number } }[];
  history: { cycle: number; time: string; regime: string; allocation: { eth: number; btc: number; usdc: number; usyc: number }; aum: number }[];
  errors: { time: string; error: string }[];
  events: { type: string; agent: string; detail: string; tx?: string; time: string }[];
}

function cn(...c: (string | undefined | false)[]) { return c.filter(Boolean).join(" "); }
function Card({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={cn("bg-white border border-circle-border rounded-2xl p-5 shadow-sm", className)}>{children}</div>;
}
function Badge({ children, variant = "default" }: { children: React.ReactNode; variant?: "default" | "success" | "error" | "warning" | "info" }) {
  const v: Record<string, string> = { default: "bg-gray-100 text-gray-600 border-gray-200", success: "bg-emerald-50 text-emerald-700 border-emerald-200", error: "bg-red-50 text-red-700 border-red-200", warning: "bg-amber-50 text-amber-700 border-amber-200", info: "bg-blue-50 text-circle-blue border-blue-200" };
  return <span className={cn("px-2 py-0.5 rounded-full text-[10px] font-semibold border", v[variant])}>{children}</span>;
}
function TierBadge({ t }: { t: number }) {
  const c = TIER_COLORS[t];
  return <span className="px-2 py-0.5 rounded-md text-[10px] font-bold" style={{ background: c + "12", color: c }}>T{t}</span>;
}
function RobustBar({ label, value }: { label: string; value: number }) {
  const p = Math.round(value * 100);
  const c = value >= 0.65 ? "#00D395" : value >= 0.4 ? "#F59E0B" : "#EF4444";
  return (
    <div className="flex items-center gap-2">
      <span className="w-5 text-[10px] font-medium text-circle-muted">{label}</span>
      <div className="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden">
        <motion.div initial={{ width: 0 }} animate={{ width: `${p}%` }} transition={{ duration: 0.8 }} className="h-full rounded-full" style={{ backgroundColor: c }} />
      </div>
      <span className="w-8 text-right text-[10px] font-mono text-circle-muted">{p}%</span>
    </div>
  );
}

function useBackendState() {
  const [data, setData] = useState<BackendState | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = () => {
    setLoading(true);
    fetch(`${API}/state`)
      .then(r => r.json())
      .then(d => { setData(d); setError(null); })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 15000);
    return () => clearInterval(interval);
  }, []);

  return { data, loading, error, refresh };
}

/* ─── Overview Tab ─── */
function OverviewTab({ data }: { data: BackendState }) {
  const allocData = Object.entries(data.allocation).map(([k, v]) => ({ name: k.toUpperCase(), value: v }));
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          { label: "AUM", value: `$${data.aum.toFixed(2)}`, sub: "USDC on Arc", icon: Wallet },
          { label: "Regime", value: data.regime, sub: `Cycle #${data.cycle}`, icon: Activity },
          { label: "Delegations", value: String(data.total_delegations), sub: `${data.total_blocks} blocked`, icon: Zap },
          { label: "Payments", value: `$${data.payments.spent.toFixed(3)}`, sub: `of $${data.payments.budget_ceiling} ceiling`, icon: TrendingUp },
        ].map((s, i) => (
          <Card key={i}>
            <div className="flex items-center justify-between mb-2">
              <span className="text-[11px] font-medium text-circle-muted">{s.label}</span>
              <s.icon className="w-4 h-4 text-circle-subtle" />
            </div>
            <p className="text-xl font-bold capitalize">{s.value}</p>
            <span className="text-[10px] text-circle-muted">{s.sub}</span>
          </Card>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card>
          <h3 className="text-sm font-semibold mb-4">Portfolio Allocation</h3>
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
                  <span className="text-sm w-12">{d.name}</span>
                  <span className="text-sm font-mono text-circle-muted">{d.value.toFixed(0)}%</span>
                </div>
              ))}
            </div>
          </div>
        </Card>

        <Card>
          <h3 className="text-sm font-semibold mb-1">Adversary Defense</h3>
          <p className="text-[11px] text-circle-muted mb-4">CGAE gate blocks unauthorized actions</p>
          <div className="space-y-3">
            <div className="flex justify-between items-center">
              <span className="text-sm">Total Attacks</span>
              <span className="text-sm font-bold">{data.adversary.total_attacks}</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-sm text-emerald-600">Blocked</span>
              <span className="text-sm font-bold text-emerald-600">{data.adversary.blocked}</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-sm">Defense Rate</span>
              <span className="text-sm font-bold">{data.adversary.total_attacks > 0 ? ((1 - data.adversary.success_rate) * 100).toFixed(0) : 0}%</span>
            </div>
            <div className="w-full h-2 bg-gray-100 rounded-full overflow-hidden mt-2">
              <div className="h-full bg-emerald-500 rounded-full" style={{ width: `${data.adversary.total_attacks > 0 ? (1 - data.adversary.success_rate) * 100 : 0}%` }} />
            </div>
          </div>
        </Card>
      </div>

      <Card>
        <div className="flex items-center gap-2 mb-3">
          <Shield className="w-4 h-4 text-circle-blue" />
          <h3 className="text-sm font-semibold">Weakest-Link Gate Function</h3>
        </div>
        <p className="text-[11px] text-circle-muted mb-4">f(R) = T<sub>k</sub> where k = min(g<sub>CC</sub>, g<sub>ER</sub>, g<sub>AS</sub>) — economic permissions bounded by worst robustness dimension</p>
        <div className="grid grid-cols-6 gap-3">
          {[0,1,2,3,4,5].map(t => (
            <div key={t} className="text-center">
              <div className="w-full h-2 rounded-full mb-1.5" style={{ background: TIER_COLORS[t] }} />
              <span className="text-[11px] font-medium">T{t}</span>
              <span className="text-[10px] text-circle-muted block">{["$0","$1","$10","$100","$1K","$10K"][t]}</span>
            </div>
          ))}
        </div>
      </Card>

      {/* Live Feed */}
      <Card>
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Activity className="w-4 h-4 text-circle-blue" />
            <h3 className="text-sm font-semibold">Live Economy Feed</h3>
          </div>
          <span className="px-2 py-0.5 rounded-full text-[9px] font-bold bg-emerald-100 text-emerald-700 border border-emerald-200 animate-pulse">LIVE</span>
        </div>
        <div className="space-y-1.5 max-h-[280px] overflow-y-auto">
          {data.events.slice().reverse().map((e, i) => {
            const styles: Record<string, { bg: string; border: string; text: string; icon: React.ReactNode }> = {
              BLOCKED: { bg: "bg-red-50", border: "border-red-200", text: "text-red-700", icon: <XCircle size={12} /> },
              PAYMENT: { bg: "bg-emerald-50", border: "border-emerald-200", text: "text-emerald-700", icon: <CheckCircle2 size={12} /> },
              REGIME: { bg: "bg-blue-50", border: "border-blue-200", text: "text-blue-700", icon: <Activity size={12} /> },
              DEMOTED: { bg: "bg-amber-50", border: "border-amber-200", text: "text-amber-700", icon: <AlertTriangle size={12} /> },
              PROMOTED: { bg: "bg-purple-50", border: "border-purple-200", text: "text-purple-700", icon: <TrendingUp size={12} /> },
            };
            const s = styles[e.type] || styles.REGIME;
            return (
              <motion.div key={`${e.time}-${i}`} initial={{ opacity: 0, x: 10 }} animate={{ opacity: 1, x: 0 }}
                className={cn("flex items-start gap-2 px-3 py-2 rounded-lg border", s.bg, s.border)}>
                <span className={cn("mt-0.5 shrink-0", s.text)}>{s.icon}</span>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className={cn("text-[10px] font-bold uppercase", s.text)}>{e.type}</span>
                    <span className="text-[10px] font-semibold text-gray-700">{e.agent}</span>
                  </div>
                  <p className="text-[10px] text-gray-600 truncate">{e.detail}</p>
                </div>
                <span className="text-[9px] text-gray-400 shrink-0">{e.time ? new Date(e.time).toLocaleTimeString() : ""}</span>
              </motion.div>
            );
          })}
          {data.events.length === 0 && <p className="text-[11px] text-circle-muted text-center py-6">Waiting for events...</p>}
        </div>
      </Card>
    </div>
  );
}
interface Trade { agent: string; task: string; amount: number; tx_hash: string; time: number }
interface TradesResponse { total: number; page: number; per_page: number; total_pages: number; trades: Trade[] }

function TradesTab({ data }: { data: BackendState }) {
  const [trades, setTrades] = useState<Trade[]>([]);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal] = useState(0);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);

  const fetchTrades = (p: number) => {
    setLoading(true);
    fetch(`${API}/trades?page=${p}&per_page=20`)
      .then(r => r.json())
      .then((d: TradesResponse) => { setTrades(d.trades); setTotalPages(d.total_pages); setTotal(d.total); setPage(d.page); })
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchTrades(1); }, []);

  const taskLabels: Record<string, string> = { regime_detection: "Regime Detection", rebalance: "Portfolio Rebalance", yield_optimization: "Yield Optimization" };

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-4 mb-2">
        <Card><span className="text-[11px] font-medium text-circle-muted">Total Trades</span><p className="text-lg font-bold mt-1">{total}</p></Card>
        <Card><span className="text-[11px] font-medium text-circle-muted">Total Paid</span><p className="text-lg font-bold text-emerald-600 mt-1">${data.payments.spent.toFixed(3)}</p></Card>
        <Card><span className="text-[11px] font-medium text-circle-muted">Attacks Blocked</span><p className="text-lg font-bold text-red-600 mt-1">{data.adversary.blocked}</p></Card>
      </div>

      <Card>
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold">Payment History (On-Chain)</h3>
          <span className="text-[10px] text-circle-muted">Page {page}/{totalPages}</span>
        </div>
        <div className="space-y-2">
          {trades.map((t, i) => (
            <div key={`${t.time}-${i}`}>
              <div onClick={() => setExpanded(expanded === i ? null : i)}
                className="flex items-center gap-3 text-xs px-4 py-3 rounded-xl border bg-white border-circle-border hover:border-circle-blue/30 cursor-pointer transition-all">
                <div className="p-1.5 rounded-lg bg-emerald-100 text-emerald-600"><CheckCircle2 size={12} /></div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold">{t.agent}</span>
                    <Badge variant="info">{taskLabels[t.task] || t.task}</Badge>
                  </div>
                </div>
                <span className="font-mono font-semibold text-emerald-600">${t.amount.toFixed(3)}</span>
                <span className="text-[10px] text-circle-muted w-16 text-right">{new Date(t.time * 1000).toLocaleTimeString()}</span>
              </div>
              <AnimatePresence>
                {expanded === i && (
                  <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }}
                    className="overflow-hidden">
                    <div className="mx-4 px-4 py-3 border border-t-0 border-circle-border rounded-b-xl bg-circle-surface space-y-2">
                      <div><span className="text-[10px] font-semibold text-circle-muted uppercase">Tx Hash</span>
                        <a href={`https://testnet.arcscan.app/tx/${t.tx_hash}`} target="_blank" rel="noopener noreferrer"
                          className="text-[11px] font-mono text-circle-blue hover:underline block mt-0.5 break-all">{t.tx_hash}</a></div>
                      <div className="flex gap-6">
                        <div><span className="text-[10px] font-semibold text-circle-muted uppercase">From</span>
                          <p className="text-[11px] font-mono mt-0.5">Treasury (0x792C...e218)</p></div>
                        <div><span className="text-[10px] font-semibold text-circle-muted uppercase">To</span>
                          <p className="text-[11px] font-mono mt-0.5">{t.agent}</p></div>
                      </div>
                      <div><span className="text-[10px] font-semibold text-circle-muted uppercase">Time</span>
                        <p className="text-[11px] mt-0.5">{new Date(t.time * 1000).toLocaleString()}</p></div>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          ))}
          {trades.length === 0 && !loading && <p className="text-sm text-circle-muted text-center py-4">No trades yet...</p>}
          {loading && <p className="text-sm text-circle-muted text-center py-4">Loading...</p>}
        </div>

        {totalPages > 1 && (
          <div className="flex items-center justify-center gap-2 mt-4 pt-4 border-t border-circle-border">
            <button onClick={() => fetchTrades(page - 1)} disabled={page <= 1}
              className="px-3 py-1.5 text-xs font-medium rounded-lg border border-circle-border disabled:opacity-30 hover:bg-circle-surface transition-colors">← Newer</button>
            <span className="text-[11px] text-circle-muted px-2">{page} / {totalPages}</span>
            <button onClick={() => fetchTrades(page + 1)} disabled={page >= totalPages}
              className="px-3 py-1.5 text-xs font-medium rounded-lg border border-circle-border disabled:opacity-30 hover:bg-circle-surface transition-colors">Older →</button>
          </div>
        )}
      </Card>
    </div>
  );
}

/* ─── Agents Tab ─── */
function AgentsTab({ data }: { data: BackendState }) {
  const roleMap: Record<string, string> = { "nova-pro": "regime_detector", "Kimi-K2.5": "rebalancer", "DeepSeek-V3.2": "yield_optimizer", "MiniMax-M2.5": "adversary" };
  const walletMap: Record<string, string> = { "nova-pro": "0x7Ca5F6d03E18434e54EB209507341C1D44e52ECD", "Kimi-K2.5": "0x3611f0BA9943e7075E14d88e557cF09E23B3317E", "DeepSeek-V3.2": "0x14DB279862f67f8179CE4722a666D6c61Db708A3", "MiniMax-M2.5": "0x0cF524195d8414Efcd9a2405495720c3EDa83577" };
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      {data.agents.map(a => (
        <Card key={a.name} className={cn(roleMap[a.name] === "adversary" && "border-red-200")}>
          <div className="flex items-start justify-between mb-3">
            <div><h3 className="text-sm font-semibold">{a.name}</h3><span className="text-[11px] text-circle-muted">{roleMap[a.name] || "agent"}</span></div>
            <TierBadge t={a.tier} />
          </div>
          <div className="flex items-center gap-2 mb-3">
            <Badge variant={roleMap[a.name] === "adversary" ? "error" : "info"}>{roleMap[a.name] || "agent"}</Badge>
            <span className="text-[11px] text-circle-muted ml-auto">${a.budget} ceiling</span>
          </div>
          {walletMap[a.name] && (
            <a href={`https://testnet.arcscan.app/address/${walletMap[a.name]}`} target="_blank" rel="noopener noreferrer"
              className="block mb-3 px-3 py-2 rounded-lg bg-circle-surface border border-circle-border hover:border-circle-blue/40 transition-colors">
              <span className="text-[10px] font-medium text-circle-muted uppercase">Wallet</span>
              <span className="text-[11px] font-mono text-circle-blue block mt-0.5 truncate">{walletMap[a.name]}</span>
            </a>
          )}
          <div className="space-y-2 pt-3 border-t border-circle-border">
            <span className="text-[10px] font-medium text-circle-muted uppercase">Robustness Vector (Real Audit Scores)</span>
            <RobustBar label="CC" value={a.scores.cc} />
            <RobustBar label="ER" value={a.scores.er} />
            <RobustBar label="AS" value={a.scores.as} />
            <RobustBar label="IH" value={a.scores.ih} />
          </div>
        </Card>
      ))}
      {data.agents.length === 0 && <Card className="col-span-2"><p className="text-sm text-circle-muted text-center py-4">Agents initializing...</p></Card>}
    </div>
  );
}

/* ─── On-Chain Tab ─── */
function OnChainTab() {
  return (
    <Card>
      <div className="flex items-center gap-3 mb-5">
        <div className="p-2.5 rounded-xl bg-blue-50 text-circle-blue"><Database size={20} /></div>
        <div><h3 className="text-sm font-semibold">Arc Testnet Registry</h3><p className="text-[11px] text-circle-muted">CGAE Protocol • Circle Developer Platform</p></div>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="space-y-4">
          {[
            { label: "CGAE Contract", value: "0xad338Ae916953D7702bc14f297D128472939880d", color: "#0052FF" },
            { label: "USDC (Circle)", value: "0x3600000000000000000000000000000000000000", color: "#00D395" },
            { label: "Treasury / Deployer", value: "0x792CD84f40f16A9C78d2586496ae8937C485e218", color: "#F59E0B" },
            { label: "Gateway Wallet", value: "0x0077777d7EBA4688BDeF3E311b846F25870A19B9", color: "#8B5CF6" },
          ].map(c => (
            <div key={c.label}>
              <span className="text-[10px] font-medium text-circle-muted uppercase">{c.label}</span>
              <code className="text-[11px] font-mono px-3 py-1.5 rounded-lg border block mt-1.5 break-all" style={{ color: c.color, background: c.color + "08", borderColor: c.color + "20" }}>{c.value}</code>
            </div>
          ))}
        </div>
        <div className="space-y-4">
          <div className="p-4 rounded-xl bg-circle-surface border border-circle-border">
            <span className="text-[10px] font-medium text-circle-muted uppercase">On-Chain State</span>
            <div className="grid grid-cols-2 gap-3 mt-3">
              <div><span className="text-[10px] text-circle-muted">Agents Certified</span><p className="text-base font-bold text-circle-blue">4</p></div>
              <div><span className="text-[10px] text-circle-muted">Chain ID</span><p className="text-base font-bold">5042002</p></div>
              <div><span className="text-[10px] text-circle-muted">Gas Token</span><p className="text-base font-bold">USDC</p></div>
              <div><span className="text-[10px] text-circle-muted">Tx Fee</span><p className="text-base font-bold">~$0.01</p></div>
            </div>
          </div>
          <div className="p-4 rounded-xl bg-circle-surface border border-circle-border">
            <span className="text-[10px] font-medium text-circle-muted uppercase">Nanopayments (x402)</span>
            <p className="text-[11px] text-circle-muted mt-2">Agent-to-agent micropayments via Gateway. Gasless, batched settlement.</p>
            <div className="flex gap-4 mt-2 text-[10px]">
              <span className="text-circle-muted">Regime: <span className="font-semibold text-circle-text">$0.01</span></span>
              <span className="text-circle-muted">Rebalance: <span className="font-semibold text-circle-text">$0.05</span></span>
              <span className="text-circle-muted">Yield: <span className="font-semibold text-circle-text">$0.005</span></span>
            </div>
          </div>
          <a href="https://testnet.arcscan.app/address/0xad338Ae916953D7702bc14f297D128472939880d" target="_blank" rel="noopener noreferrer"
            className="block w-full py-3 rounded-xl bg-circle-blue text-white font-bold text-xs uppercase text-center hover:bg-circle-blue-light transition-colors">
            View on Arc Explorer ↗
          </a>
        </div>
      </div>
    </Card>
  );
}

/* ─── Main Page ─── */
const TABS = ["Overview", "Trades", "Agents", "On-Chain"] as const;
type Tab = typeof TABS[number];

export default function Dashboard() {
  const [tab, setTab] = useState<Tab>("Overview");
  const { data, loading, error, refresh } = useBackendState();

  return (
    <div className="min-h-screen flex flex-col">
      <header className="bg-circle-blue-bg text-white px-6 py-4">
        <div className="max-w-5xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Shield className="w-6 h-6 text-circle-blue-light" />
            <div>
              <h1 className="text-base font-bold">CGAE Perpetual Economy</h1>
              <p className="text-[10px] text-white/60">Arc × Circle • Adaptive Portfolio Manager</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            {data && <span className="text-[10px] text-white/60">Cycle #{data.cycle}</span>}
            <button onClick={refresh} className="p-1.5 rounded-lg hover:bg-white/10 transition-colors">
              <RefreshCw className={cn("w-4 h-4", loading && "animate-spin")} />
            </button>
            <Badge variant={data?.status === "running" ? "success" : data?.status === "error" ? "error" : "warning"}>
              {data?.status || "connecting..."}
            </Badge>
          </div>
        </div>
      </header>

      <main className="flex-1 max-w-5xl mx-auto w-full px-6 py-6">
        <nav className="flex gap-1 mb-6 border-b border-circle-border">
          {TABS.map(t => (
            <button key={t} onClick={() => setTab(t)}
              className={cn("px-4 py-2.5 text-sm font-medium transition-all border-b-2 -mb-px",
                tab === t ? "border-circle-blue text-circle-blue" : "border-transparent text-circle-muted hover:text-circle-text")}>
              {t}
            </button>
          ))}
        </nav>

        {error && !data && (
          <Card className="border-amber-200 bg-amber-50">
            <div className="flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-amber-600" />
              <span className="text-sm text-amber-700">Backend connecting... ({error})</span>
            </div>
            <p className="text-[11px] text-amber-600 mt-2">The backend may be cold-starting. It takes ~60s on first load.</p>
          </Card>
        )}

        {data && (
          <AnimatePresence mode="wait">
            <motion.div key={tab} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.15 }}>
              {tab === "Overview" && <OverviewTab data={data} />}
              {tab === "Trades" && <TradesTab data={data} />}
              {tab === "Agents" && <AgentsTab data={data} />}
              {tab === "On-Chain" && <OnChainTab />}
            </motion.div>
          </AnimatePresence>
        )}
      </main>

      <footer className="bg-circle-blue-bg text-white/60 px-6 py-4 mt-auto">
        <div className="max-w-5xl mx-auto text-center">
          <p className="text-[11px]">
            Based on <a href="https://arxiv.org/abs/2603.15639" className="text-circle-blue-light hover:underline">The Comprehension-Gated Agent Economy</a> (Baxi, 2026) • Powered by Circle &amp; Arc
          </p>
        </div>
      </footer>
    </div>
  );
}
