import { spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { test, expect } from "@playwright/test";

function withFixture(source: string, check: (path: string) => void) {
  const directory = mkdtempSync(join(tmpdir(), "bank-quality-"));
  const path = join(directory, "fixture.ts");
  try {
    writeFileSync(path, source);
    check(path);
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
}

function lint(path: string) {
  return spawnSync(
    resolve("node_modules/.bin/oxlint"),
    ["--config", resolve(".oxlintrc.json"), "--max-warnings", "0", path],
    { encoding: "utf8", timeout: 10_000 },
  );
}

const violations = [
  {
    rule: "complexity",
    source: `export function classify(value: number) { ${Array.from(
      { length: 10 },
      (_, i) => `if (value === ${i}) return ${i};`,
    ).join(" ")} return -1; }`,
  },
  {
    rule: "max-depth",
    source:
      "export function nested(value: number) { if (value > 0) { if (value > 1) { if (value > 2) { if (value > 3) { return value; } } } } return 0; }",
  },
  {
    rule: "max-params",
    source:
      "export function parameters(a: number, b: number, c: number, d: number, e: number) { return a + b + c + d + e; }",
  },
  {
    rule: "max-nested-callbacks",
    source:
      "export function callbacks() { [1].map(() => [2].map(() => [3].map(() => [4].map(() => 5)))); }",
  },
];

for (const { rule, source } of violations) {
  test(`Oxlint enforces ${rule} with the committed configuration`, () => {
    withFixture(source, (path) => {
      const result = lint(path);
      expect(result.error).toBeUndefined();
      expect(result.status).toBe(1);
      expect(result.stdout + result.stderr).toContain(rule);
    });
  });
}

test("Oxlint accepts a valid function", () => {
  withFixture("export function identity(value: number) { return value; }", (path) => {
    const result = lint(path);
    expect(result.error).toBeUndefined();
    expect(result.status).toBe(0);
  });
});

test("Oxfmt check rejects bad formatting without modifying files", () => {
  const source = "export const value={one:1,two:2}";
  withFixture(source, (path) => {
    const run = (mode: string) =>
      spawnSync(
        resolve("node_modules/.bin/oxfmt"),
        ["--config", resolve("../.oxfmtrc.json"), mode, path],
        { encoding: "utf8", timeout: 10_000 },
      );
    const bad = run("--check");
    expect(bad.error).toBeUndefined();
    expect(bad.status).toBe(1);
    expect(readFileSync(path, "utf8")).toBe(source);
    expect(run("--write").status).toBe(0);
    expect(readFileSync(path, "utf8")).not.toBe(source);
    expect(run("--check").status).toBe(0);
  });
});
