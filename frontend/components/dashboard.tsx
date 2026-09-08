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
    [selected, setSelected] = useState<Transfer | null>(
      initialSelection ?? null,
    );
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
        setError(e instanceof Error ? e.message : "Error inesperado");
      }
    });
  }
  function refresh() {
    run(async () => {
      setActions(await refreshTransfers());
      if (selected) setSelected(await getTransfer(selected.id));
      setNotice("Estados actualizados");
    });
  }
  function select(action: Transfer) {
    setChecked(false);
    run(async () => setSelected(await getTransfer(action.id)));
  }
  function decision(value: "confirm" | "reject") {
    if (!selected) return;
    run(async () => {
      await decide(selected.id, selected.fingerprint, value);
      setActions(await refreshTransfers());
      setSelected(await getTransfer(selected.id));
      setChecked(false);
      setNotice(
        value === "confirm"
          ? "Transferencia simulada correctamente. No se ha movido dinero real."
          : "Acción rechazada.",
      );
    });
  }
  const waiting = actions.filter(
    (a) => a.status === "pending" && a.expires_at * 1000 > now,
  );
  const visible = actions.filter(
    (a) =>
      filter === "all" ||
      (filter === "pending" ? a.status === "pending" : a.status !== "pending"),
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
            Bank Assistant<small>Espacio de evaluación</small>
          </div>
          <ChevronRight size={16} />
        </div>
        <span className="nav-label">WORKSPACE</span>
        <button
          className={filter !== "history" ? "nav active" : "nav"}
          onClick={() => setFilter("all")}
        >
          <LayoutDashboard size={18} /> Centro de control
        </button>
        <button
          className={filter === "history" ? "nav active" : "nav"}
          onClick={() => setFilter("history")}
        >
          <History size={18} /> Historial de acciones
        </button>
        <div className="sidebar-bottom">
          <div className="sandbox">
            <ShieldCheck size={21} />
            <strong>Un espacio seguro</strong>
            <p>
              Todas las operaciones son simuladas. Tú decides qué se ejecuta.
            </p>
            <span>
              <i /> Modo sandbox
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
            <LogOut size={17} /> Cerrar sesión
          </button>
          <div className="profile">
            <span>MD</span>
            <div>
              Revisor humano<small>Acceso de evaluación</small>
            </div>
          </div>
        </div>
      </aside>
      <div className="main">
        <header>
          <div>
            Workspace <ChevronRight size={14} />{" "}
            <strong>Centro de control</strong>
          </div>
          <span className="environment">
            <i /> Entorno de simulación
          </span>
        </header>
        <main>
          <div className="title-row">
            <div>
              <span className="eyebrow">SUPERVISIÓN DEL ASISTENTE</span>
              <h1>
                Centro de control<span>.</span>
              </h1>
              <p>La inteligencia propone. Tú tienes el control.</p>
            </div>
            <button className="secondary" disabled={pending} onClick={refresh}>
              <RefreshCw size={16} className={pending ? "spin" : ""} />{" "}
              Actualizar
            </button>
          </div>
          <section className="hero">
            <div>
              <span className="hero-tag">
                <ShieldCheck size={15} /> CONFIRMACIÓN HUMANA
              </span>
              <h2>Cada acción, con tu aprobación.</h2>
              <p>
                Revisa los detalles antes de confirmar.
                <br />
                El asistente nunca puede autorizar una transferencia.
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
          <section className="stats" aria-label="Resumen">
            <article>
              <span>
                Pendientes de revisión <Clock3 size={18} />
              </span>
              <strong>{waiting.length.toString().padStart(2, "0")}</strong>
              <small>Necesitan tu confirmación</small>
            </article>
            <article>
              <span>
                Simulaciones completadas <ArrowUpRight size={18} />
              </span>
              <strong>
                {actions
                  .filter((a) => a.status === "executed")
                  .length.toString()
                  .padStart(2, "0")}
              </strong>
              <small>Sin movimientos de dinero real</small>
            </article>
            <article>
              <span>
                Control de ejecución <ShieldCheck size={18} />
              </span>
              <strong className="stat-word">Humano</strong>
              <small>Confirmación fuera del MCP</small>
            </article>
          </section>
          {error && (
            <div className="error banner" role="alert">
              {error}
            </div>
          )}
          <p className="sr-only" role="status">
            {notice}
          </p>
          <div className="section-title">
            <div>
              <h2>Actividad del asistente</h2>
              <p>Propuestas, decisiones y un registro de cada paso.</p>
            </div>
            <span className="count">{actions.length} acciones</span>
          </div>
          <div className="tabs" aria-label="Filtrar acciones">
            {[
              ["all", "Todas las acciones"],
              ["pending", "Por confirmar"],
              ["history", "Finalizadas"],
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
                  <h3>Todo bajo control</h3>
                  <p>
                    {filter === "all"
                      ? "Las propuestas del agente aparecerán aquí. Conecta el MCP o ejecuta el escenario local de demostración."
                      : "No hay acciones en esta vista."}
                  </p>
                  <span>Esperando propuestas del asistente</span>
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
                      <span className={`badge ${action.status}`}>
                        {labels[action.status]}
                      </span>
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
              <ShieldCheck size={14} /> Diseñado para mantenerte al mando
            </span>
            <span>Bank Assistant · Reto B / MCP</span>
          </footer>
        </main>
      </div>
    </div>
  );
}
