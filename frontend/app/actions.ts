"use server";
import { cookies } from "next/headers";
import { revalidatePath } from "next/cache";
import { api, passwordMatches, startSession } from "@/lib/server";
import type { Transfer } from "@/lib/types";
import { isActionId, isFingerprint } from "@/lib/validation";

export async function login(form: FormData): Promise<string | null> {
  const password = form.get("password");
  if (
    typeof password !== "string" ||
    password.length > 256 ||
    !passwordMatches(password)
  ) {
    return "La contraseña no es correcta.";
  }
  await startSession();
  revalidatePath("/");
  return null;
}
export async function logout() {
  (await cookies()).delete("review_session");
  revalidatePath("/");
}
export async function refreshTransfers() {
  return api<Transfer[]>("/actions");
}
export async function getTransfer(id: string) {
  if (!isActionId(id)) throw new Error("Identificador no válido");
  return api<Transfer>(`/actions/${id}`);
}
export async function decide(
  id: string,
  fingerprint: string,
  decision: "confirm" | "reject",
) {
  if (
    !isActionId(id) ||
    !isFingerprint(fingerprint) ||
    !["confirm", "reject"].includes(decision)
  ) {
    throw new Error("Solicitud no válida");
  }
  const result = await api<Transfer>(`/actions/${id}/decision`, {
    fingerprint,
    decision,
  });
  revalidatePath("/");
  return result;
}
