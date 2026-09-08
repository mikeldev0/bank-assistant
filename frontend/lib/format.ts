export const labels = {
  pending: "Awaiting confirmation",
  executed: "Simulated",
  rejected: "Rejected",
  expired: "Expired",
};
export const events: Record<string, string> = {
  proposed: "Agent proposed the action",
  confirmed: "Human confirmation received",
  executed: "Simulation completed",
  rejected: "Action rejected",
  expired: "Confirmation window expired",
};
export const money = (cents: number) =>
  new Intl.NumberFormat("en-IE", { style: "currency", currency: "EUR" }).format(cents / 100);
export const date = (value: number) =>
  new Date(value * 1000).toLocaleString("en-IE", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
