import { test, expect } from "@playwright/test";
import { SESSION_TTL_MS, signSession, verifySession } from "../lib/session";
import { isActionId, isFingerprint } from "../lib/validation";

const secret = "s".repeat(48);
const now = 1_800_000_000_000;

test("session signatures expire at the exact boundary", () => {
  const value = signSession(secret, now);
  expect(verifySession(value, secret, now)).toBe(true);
  expect(verifySession(value, secret, now + SESSION_TTL_MS - 1)).toBe(true);
  expect(verifySession(value, secret, now + SESSION_TTL_MS)).toBe(false);
  expect(verifySession(value, "different".repeat(8), now)).toBe(false);
});

test("malformed cookies are rejected without throwing", () => {
  const signed = signSession(secret, now);
  for (const value of [
    undefined, "", `${signed}.suffix`, `${signed}\n`,
    `${now + SESSION_TTL_MS}.${"\u00e9".repeat(64)}`,
    `${now + SESSION_TTL_MS}.${"g".repeat(64)}`,
    `Infinity.${"a".repeat(64)}`, `1e30.${"a".repeat(64)}`,
    `${now + SESSION_TTL_MS}.${"a".repeat(63)}`,
  ]) {
    expect(() => verifySession(value, secret, now)).not.toThrow();
    expect(verifySession(value, secret, now)).toBe(false);
  }
});

test("server action identifiers reject coercion and malformed UUIDs", () => {
  const id = "12345678-1234-4123-8123-123456789abc";
  expect(isActionId(id)).toBe(true);
  for (const value of [undefined, null, [id], "-".repeat(36), `${id}\n`, id.replace("-4123-", "-0123-")]) {
    expect(isActionId(value)).toBe(false);
  }
  expect(isFingerprint("a".repeat(64))).toBe(true);
  expect(isFingerprint(["a".repeat(64)])).toBe(false);
  expect(isFingerprint(`${"a".repeat(64)}\n`)).toBe(false);
});
