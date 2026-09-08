import { authenticated, api } from "@/lib/server";
import type { Transfer } from "@/lib/types";
import { Dashboard } from "@/components/dashboard";
import { Login } from "@/components/login";
export const dynamic = "force-dynamic";
export default async function Page({
  searchParams,
}: {
  searchParams: Promise<{ action?: string | string[] }>;
}) {
  if (!(await authenticated())) return <Login />;
  const { action } = await searchParams;
  let actions: Transfer[] = [],
    selected: Transfer | undefined,
    error: string | undefined;
  try {
    actions = await api<Transfer[]>("/actions");
    if (action !== undefined) {
      if (typeof action !== "string" || !/^[0-9a-f-]{36}$/.test(action)) {
        error = "El enlace de revisión no contiene una referencia válida.";
      } else {
        selected = await api<Transfer>(`/actions/${action}`);
      }
    }
  } catch {
    error =
      "No se puede conectar con el gateway. Comprueba que el backend esté disponible.";
  }
  return (
    <Dashboard
      key={selected?.id ?? "dashboard"}
      initial={actions}
      initialError={error}
      initialSelection={selected}
    />
  );
}
