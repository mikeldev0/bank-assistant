"use client";
import { ArrowDownLeft, Clock3, ShieldCheck, X } from "lucide-react";
import type { Transfer } from "@/lib/types";
import { labels, money, date, events } from "@/lib/format";

export function TransferReview({
  selected,
  checked,
  pending,
  remaining,
  onClose,
  onChecked,
  onDecision,
}: {
  selected: Transfer | null;
  checked: boolean;
  pending: boolean;
  remaining: number;
  onClose: () => void;
  onChecked: (checked: boolean) => void;
  onDecision: (decision: "confirm" | "reject") => void;
}) {
  return (
    <aside className="detail" aria-label="Detalle de acción">
      {selected ? (
        <>
          <div className="detail-title">
            <span className="eyebrow">REVISIÓN DE TRANSFERENCIA</span>
            <button className="icon-button" aria-label="Cerrar detalle" onClick={onClose}>
              <X size={18} />
            </button>
          </div>
          <h2>{money(selected.amount_cents)}</h2>
          <span className={`badge ${selected.status}`}>{labels[selected.status]}</span>
          <dl>
            <div>
              <dt>Beneficiario</dt>
              <dd>{selected.recipient}</dd>
            </div>
            <div>
              <dt>Cuenta de prueba</dt>
              <dd>{selected.destination}</dd>
            </div>
            <div>
              <dt>Concepto</dt>
              <dd>{selected.concept}</dd>
            </div>
            <div>
              <dt>Referencia</dt>
              <dd className="mono">{selected.id.slice(0, 8)}</dd>
            </div>
          </dl>
          {selected.status === "pending" && (
            <>
              <p className="expires">
                <Clock3 size={14} />
                {remaining
                  ? `Caduca en ${Math.floor(remaining / 60)}:${String(remaining % 60).padStart(2, "0")}`
                  : "Confirmación caducada"}
              </p>
              <label className="confirmation">
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={(e) => onChecked(e.target.checked)}
                />
                He revisado el importe y el destinatario. Confirmo esta simulación.
              </label>
              <button
                className="confirm-button"
                disabled={!checked || pending || !remaining}
                onClick={() => onDecision("confirm")}
              >
                <ShieldCheck size={17} />
                Confirmar simulación
              </button>
              <button
                className="reject-button"
                disabled={pending || !remaining}
                onClick={() => onDecision("reject")}
              >
                Rechazar propuesta
              </button>
            </>
          )}
          <div className="audit">
            <h3>Trazabilidad</h3>
            {selected.audit?.map((event, i) => (
              <div key={i}>
                <span className="audit-dot" />
                <p>
                  {events[event.event] ?? event.event}
                  <small>
                    {date(event.at)} · {event.actor}
                  </small>
                </p>
              </div>
            ))}
          </div>
        </>
      ) : (
        <div className="detail-empty">
          <ArrowDownLeft size={25} />
          <h3>Los detalles importan.</h3>
          <p>Selecciona una acción para revisar sus datos y consultar su trazabilidad.</p>
          <div>
            <ShieldCheck size={16} /> Verificación antes de ejecución
          </div>
        </div>
      )}
    </aside>
  );
}
