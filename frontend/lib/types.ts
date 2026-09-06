export type AuditEvent = { event: string; actor: string; at: number };
export type Transfer = {
  id: string;
  recipient: string;
  destination: string;
  amount_cents: number;
  concept: string;
  currency: "EUR";
  status: "pending" | "executed" | "rejected" | "expired";
  created_at: number;
  expires_at: number;
  fingerprint: string;
  simulated: true;
  audit?: AuditEvent[];
};
