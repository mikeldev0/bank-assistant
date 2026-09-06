import "server-only";
import { createHmac, timingSafeEqual } from "node:crypto";
import { cookies } from "next/headers";

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
  const expires = String(Date.now() + 8 * 60 * 60 * 1000);
  const signature = createHmac("sha256", required("SESSION_SECRET"))
    .update(expires)
    .digest("hex");
  (await cookies()).set("review_session", `${expires}.${signature}`, {
    httpOnly: true,
    sameSite: "strict",
    secure: process.env.COOKIE_SECURE !== "false",
    path: "/",
    maxAge: 8 * 60 * 60,
  });
}
export async function authenticated() {
  const value = (await cookies()).get("review_session")?.value;
  if (!value) return false;
  const [expires, signature] = value.split(".");
  if (
    !expires ||
    !signature ||
    !/^\d+$/.test(expires) ||
    Date.now() > Number(expires)
  )
    return false;
  const expected = createHmac("sha256", required("SESSION_SECRET"))
    .update(expires)
    .digest("hex");
  return (
    signature.length === expected.length &&
    timingSafeEqual(Buffer.from(signature), Buffer.from(expected))
  );
}
export async function api<T>(path: string, body?: unknown): Promise<T> {
  if (!(await authenticated()))
    throw new Error("Inicia sesión para revisar las acciones.");
  const response = await fetch(
    `${process.env.BACKEND_URL ?? "http://127.0.0.1:8000"}${path}`,
    {
      method: body ? "POST" : "GET",
      headers: {
        Authorization: `Bearer ${required("REVIEWER_TOKEN")}`,
        "Content-Type": "application/json",
      },
      body: body ? JSON.stringify(body) : undefined,
      cache: "no-store",
      signal: AbortSignal.timeout(10_000),
    },
  );
  if (!response.ok) {
    if (response.status === 409)
      throw new Error(
        "La acción ha caducado o ya cambió de estado. Actualiza la lista.",
      );
    throw new Error(
      "No se ha podido completar la operación. Inténtalo de nuevo.",
    );
  }
  return response.json() as Promise<T>;
}
