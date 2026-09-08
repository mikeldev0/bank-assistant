export const labels = {
  pending: "Por confirmar",
  executed: "Simulada",
  rejected: "Rechazada",
  expired: "Caducada",
};
export const events: Record<string, string> = {
  proposed: "El agente propuso la acción",
  confirmed: "Confirmación humana recibida",
  executed: "Simulación completada",
  rejected: "Acción rechazada",
  expired: "Plazo de confirmación agotado",
};
export const money = (cents: number) =>
  new Intl.NumberFormat("es-ES", { style: "currency", currency: "EUR" }).format(cents / 100);
export const date = (value: number) =>
  new Date(value * 1000).toLocaleString("es-ES", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
