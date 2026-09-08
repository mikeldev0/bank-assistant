import "server-only";
import { createHmac, timingSafeEqual } from "node:crypto";
import { cookies } from "next/headers";
import { SESSION_TTL_MS, signSession, verifySession } from "@/lib/session";

function required(name: string): string {
  const value = process.env[name];
  if (!value || value.length < 32) throw new Error(`Missing or short ${name}`);
  return value;
}
export function passwordMatches(value: string) {
  const hash = (text: string) =>
    createHmac("sha256", required("SESSION_SECRET")).update(text).digest();
  return timingSafeEqual(hash(value), hash(required("REVIEW_PASSWORD")));
}
export async function startSession() {
  (await cookies()).set("review_session", signSession(required("SESSION_SECRET")), {
    httpOnly: true,
    sameSite: "strict",
    secure: process.env.COOKIE_SECURE !== "false",
    path: "/",
    maxAge: SESSION_TTL_MS / 1000,
  });
}
export async function authenticated() {
  const value = (await cookies()).get("review_session")?.value;
  if (!value) return false;
  return verifySession(value, required("SESSION_SECRET"));
}
export async function api<T>(path: string, body?: unknown): Promise<T> {
  if (!(await authenticated())) throw new Error("Inicia sesión para revisar las acciones.");
  const response = await fetch(`${process.env.BACKEND_URL ?? "http://127.0.0.1:8000"}${path}`, {
    method: body ? "POST" : "GET",
    headers: {
      Authorization: `Bearer ${required("REVIEWER_TOKEN")}`,
      "Content-Type": "application/json",
    },
    body: body ? JSON.stringify(body) : undefined,
    cache: "no-store",
    signal: AbortSignal.timeout(10_000),
  });
  if (!response.ok) {
    if (response.status === 409)
      throw new Error("La acción ha caducado o ya cambió de estado. Actualiza la lista.");
    throw new Error("No se ha podido completar la operación. Inténtalo de nuevo.");
  }
  return response.json() as Promise<T>;
}
