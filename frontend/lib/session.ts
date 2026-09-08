import { createHmac, timingSafeEqual } from "node:crypto";

export const SESSION_TTL_MS = 8 * 60 * 60 * 1000;

export function signSession(secret: string, now = Date.now()): string {
  const expires = String(now + SESSION_TTL_MS);
  const signature = createHmac("sha256", secret).update(expires).digest("hex");
  return `${expires}.${signature}`;
}

export function verifySession(
  value: string | undefined,
  secret: string,
  now = Date.now(),
): boolean {
  if (typeof value !== "string") return false;
  // Exact grammar prevents ignored suffixes, non-ASCII signatures, NaN and
  // mismatched buffer lengths from reaching timingSafeEqual.
  const match = /^([0-9]{13})\.([a-f0-9]{64})$/.exec(value);
  if (!match || match[0] !== value || Number(match[1]) <= now) return false;
  const expected = createHmac("sha256", secret).update(match[1]).digest();
  return timingSafeEqual(Buffer.from(match[2], "hex"), expected);
}
