import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const FORBIDDEN = ["expected_answer", "evaluation_rubric", "correct_option", "answer_key", "any_of"];

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = path.join(dir, name);
    return statSync(full).isDirectory() ? walk(full) : [full];
  });
}

describe("answer-key boundary", () => {
  it("never references answer-key fields in app source or in the API contract it is generated from", () => {
    const src = path.resolve(__dirname, "..");
    const files = [...walk(src).filter((f) => /\.(ts|tsx)$/.test(f) && !f.endsWith("no-answer-keys.test.ts"))];
    const spec = path.resolve(__dirname, "../../openapi.json");
    for (const file of [...files, spec]) {
      const text = readFileSync(file, "utf8");
      for (const word of FORBIDDEN) expect(text, `${file} mentions ${word}`).not.toContain(word);
    }
  });
});
