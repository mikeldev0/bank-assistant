"use client";
import { useEffect, useState, useTransition } from "react";
import {
  Activity,
  ArrowUpRight,
  Check,
  Clock3,
  ChevronRight,
  History,
  LayoutDashboard,
  LogOut,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";
import { decide, getTransfer, logout, refreshTransfers } from "@/app/actions";
import { TransferReview } from "@/components/transfer-review";
import { labels, money, date } from "@/lib/format";
import type { Transfer } from "@/lib/types";
export function Dashboard({
  initial,
  initialError,
  initialSelection,
}: {
  initial: Transfer[];
  initialError?: string;
  initialSelection?: Transfer;
}) {
  const [actions, setActions] = useState(initial),
    [selected, setSelected] = useState<Transfer | null>(initialSelection ?? null);
  const [filter, setFilter] = useState("all"),
    [checked, setChecked] = useState(false);
  const [error, setError] = useState(initialError),
    [notice, setNotice] = useState("");
  const [pending, startTransition] = useTransition();
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  function run(operation: () => Promise<void>) {
    setError(undefined);
    startTransition(async () => {
      try {
        await operation();
      } catch (e) {
        setError(e instanceof Error ? e.message : "Unexpected error");
      }
    });
  }
  function refresh() {
    run(async () => {
      setActions(await refreshTransfers());
      if (selected) setSelected(await getTransfer(selected.id));
      setNotice("Statuses updated");
    });
  }
  function select(action: Transfer) {
    setChecked(false);
    run(async () => setSelected(await getTransfer(action.id)));
  }
  function decision(value: "confirm" | "reject") {
    if (!selected || pending || (value === "confirm" && !checked)) return;
    run(async () => {
      const result = await decide(selected.id, selected.fingerprint, value);
      setSelected(result);
      setActions((current) => current.map((action) => (action.id === result.id ? result : action)));
      setChecked(false);
      setNotice(
        value === "confirm"
          ? "Simulated transfer completed. No real money was moved."
          : "Action rejected.",
      );
      // Failure to refresh the audit cannot make a committed decision pending again.
      setSelected(await getTransfer(result.id));
      setActions(await refreshTransfers());
    });
  }
  const waiting = actions.filter((a) => a.status === "pending");
  const visible = actions.filter(
    (a) =>
      filter === "all" || (filter === "pending" ? a.status === "pending" : a.status !== "pending"),
  );
  const remaining = selected
    ? Math.max(0, Math.ceil((selected.expires_at * 1000 - now) / 1000))
    : 0;
  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-icon">b.</span> bank assistant
        </div>
        <div className="workspace">
          <span className="workspace-avatar">B</span>
          <div>
            Bank Assistant<small>Evaluation workspace</small>
          </div>
          <ChevronRight size={16} />
        </div>
        <span className="nav-label">WORKSPACE</span>
        <button
          className={filter !== "history" ? "nav active" : "nav"}
          onClick={() => setFilter("all")}
        >
          <LayoutDashboard size={18} /> Control Center
        </button>
        <button
          className={filter === "history" ? "nav active" : "nav"}
          onClick={() => setFilter("history")}
        >
          <History size={18} /> Action history
        </button>
        <div className="sidebar-bottom">
          <div className="sandbox">
            <ShieldCheck size={21} />
            <strong>A secure workspace</strong>
            <p>All operations are simulated. You decide what gets executed.</p>
            <span>
              <i /> Sandbox mode
            </span>
          </div>
          <button
            className="nav"
            onClick={() =>
              run(async () => {
                await logout();
              })
            }
          >
            <LogOut size={17} /> Sign out
          </button>
          <div className="profile">
            <span>MD</span>
            <div>
              Human reviewer<small>Evaluation access</small>
            </div>
          </div>
        </div>
      </aside>
      <div className="main">
        <header>
          <div>
            Workspace <ChevronRight size={14} /> <strong>Control Center</strong>
          </div>
          <span className="environment">
            <i /> Simulation environment
          </span>
        </header>
        <main>
          <div className="title-row">
            <div>
              <span className="eyebrow">ASSISTANT OVERSIGHT</span>
              <h1>
                Control Center<span>.</span>
              </h1>
              <p>The assistant proposes. You stay in control.</p>
            </div>
            <button className="secondary" disabled={pending} onClick={refresh}>
              <RefreshCw size={16} className={pending ? "spin" : ""} /> Refresh
            </button>
          </div>
          <section className="hero">
            <div>
              <span className="hero-tag">
                <ShieldCheck size={15} /> HUMAN CONFIRMATION
              </span>
              <h2>Every action, with your approval.</h2>
              <p>
                Review the details before confirming.
                <br />
                The assistant can never authorize a transfer.
              </p>
            </div>
            <div className="hero-art" aria-hidden="true">
              <div className="orbit" />
              <div className="shield">
                <ShieldCheck size={58} strokeWidth={1.3} />
              </div>
              <span className="art-check">
                <Check size={19} />
              </span>
            </div>
          </section>
          <section className="stats" aria-label="Summary">
            <article>
              <span>
                Pending review <Clock3 size={18} />
              </span>
              <strong>{waiting.length.toString().padStart(2, "0")}</strong>
              <small>Need your confirmation</small>
            </article>
            <article>
              <span>
                Completed simulations <ArrowUpRight size={18} />
              </span>
              <strong>
                {actions
                  .filter((a) => a.status === "executed")
                  .length.toString()
                  .padStart(2, "0")}
              </strong>
              <small>No real money movement</small>
            </article>
            <article>
              <span>
                Execution control <ShieldCheck size={18} />
              </span>
              <strong className="stat-word">Human</strong>
              <small>Confirmation outside the MCP</small>
            </article>
          </section>
          {error && (
            <div className="error banner" role="alert">
              {error}
            </div>
          )}
          <output className="sr-only">{notice}</output>
          <div className="section-title">
            <div>
              <h2>Assistant activity</h2>
              <p>Proposals, decisions, and a record of every step.</p>
            </div>
            <span className="count">{actions.length} actions</span>
          </div>
          <div className="tabs" aria-label="Filter actions">
            {[
              ["all", "All actions"],
              ["pending", "Awaiting confirmation"],
              ["history", "Completed"],
            ].map(([value, label]) => (
              <button
                key={value}
                aria-pressed={filter === value}
                onClick={() => setFilter(value)}
                className={filter === value ? "selected" : ""}
              >
                {label}
                {value === "pending" && <span>{waiting.length}</span>}
              </button>
            ))}
          </div>
          <section className="activity-grid">
            <div className="action-list">
              {visible.length === 0 ? (
                <div className="empty">
                  <Activity size={28} />
                  <h3>All under control</h3>
                  <p>
                    {filter === "all"
                      ? "Agent proposals will appear here. Connect the MCP or run the local demo scenario."
                      : "No actions in this view."}
                  </p>
                  <span>Waiting for assistant proposals</span>
                </div>
              ) : (
                visible.map((action) => (
                  <button
                    key={action.id}
                    className={`action-row ${selected?.id === action.id ? "focused" : ""}`}
                    onClick={() => select(action)}
                    disabled={pending}
                  >
                    <span className="transfer-icon">
                      <ArrowUpRight size={20} />
                    </span>
                    <div>
                      <strong>{action.recipient}</strong>
                      <small>{action.concept}</small>
                      <span className={`badge ${action.status}`}>{labels[action.status]}</span>
                    </div>
                    <div className="amount">
                      <strong>{money(action.amount_cents)}</strong>
                      <small>{date(action.created_at)}</small>
                    </div>
                    <ChevronRight size={16} />
                  </button>
                ))
              )}
            </div>
            <TransferReview
              selected={selected}
              checked={checked}
              pending={pending}
              remaining={remaining}
              onClose={() => setSelected(null)}
              onChecked={setChecked}
              onDecision={decision}
            />
          </section>
          <footer>
            <span>
              <ShieldCheck size={14} /> Designed to keep you in control
            </span>
            <span>Bank Assistant · Challenge B / MCP</span>
          </footer>
        </main>
      </div>
    </div>
  );
}
