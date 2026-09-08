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
    <aside className="detail" aria-label="Action details">
      {selected ? (
        <>
          <div className="detail-title">
            <span className="eyebrow">TRANSFER REVIEW</span>
            <button className="icon-button" aria-label="Close details" onClick={onClose}>
              <X size={18} />
            </button>
          </div>
          <h2>{money(selected.amount_cents)}</h2>
          <span className={`badge ${selected.status}`}>{labels[selected.status]}</span>
          <dl>
            <div>
              <dt>Recipient</dt>
              <dd>{selected.recipient}</dd>
            </div>
            <div>
              <dt>Test account</dt>
              <dd>{selected.destination}</dd>
            </div>
            <div>
              <dt>Concept</dt>
              <dd>{selected.concept}</dd>
            </div>
            <div>
              <dt>Reference</dt>
              <dd className="mono">{selected.id.slice(0, 8)}</dd>
            </div>
          </dl>
          {selected.status === "pending" && (
            <>
              <p className="expires">
                <Clock3 size={14} />
                {remaining
                  ? `Expires in ${Math.floor(remaining / 60)}:${String(remaining % 60).padStart(2, "0")}`
                  : "Confirmation expired"}
              </p>
              <label className="confirmation">
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={(e) => onChecked(e.target.checked)}
                />
                I have reviewed the amount and recipient. I confirm this simulation.
              </label>
              <button
                className="confirm-button"
                disabled={!checked || pending || !remaining}
                onClick={() => onDecision("confirm")}
              >
                <ShieldCheck size={17} />
                Confirm simulation
              </button>
              <button
                className="reject-button"
                disabled={pending || !remaining}
                onClick={() => onDecision("reject")}
              >
                Reject proposal
              </button>
            </>
          )}
          <div className="audit">
            <h3>Audit trail</h3>
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
          <h3>Details matter.</h3>
          <p>Select an action to review its data and audit trail.</p>
          <div>
            <ShieldCheck size={16} /> Verification before execution
          </div>
        </div>
      )}
    </aside>
  );
}
