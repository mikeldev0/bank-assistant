import { authenticated, api } from "@/lib/server";
import type { Transfer } from "@/lib/types";
import { Dashboard } from "@/components/dashboard";
import { Login } from "@/components/login";
export const dynamic = "force-dynamic";
export default async function Page() {
  if (!(await authenticated())) return <Login />;
  let actions: Transfer[] = [],
    error: string | undefined;
  try {
    actions = await api<Transfer[]>("/actions");
  } catch {
    error =
      "No se puede conectar con el gateway. Comprueba que el backend esté disponible.";
  }
  return <Dashboard initial={actions} initialError={error} />;
}
