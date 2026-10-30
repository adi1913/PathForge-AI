import { describe, expect, it } from "vitest";
import { formatConfidence, formatMinutes, formatPercent, formatSignedDelta, humanize, toneFor } from "./utils";

describe("format helpers", () => {
  it("humanizes enum values", () => {
    expect(humanize("in_progress")).toBe("In progress");
    expect(humanize(null)).toBe("");
  });
  it("formats numbers defensively", () => {
    expect(formatPercent(42.4)).toBe("42%");
    expect(formatPercent(null)).toBe("n/a");
    expect(formatConfidence(0.456)).toBe("0.46");
    expect(formatConfidence(undefined)).toBe("n/a");
    expect(formatSignedDelta(0.1)).toBe("+0.10");
    expect(formatSignedDelta(-0.05)).toBe("-0.05");
    expect(formatSignedDelta(0)).toBe("0.00");
    expect(formatMinutes(45)).toBe("45 min");
    expect(formatMinutes(150)).toBe("2 h 30 min");
    expect(formatMinutes(null)).toBe("-");
  });
  it("maps statuses to tones", () => {
    expect(toneFor("completed")).toBe("success");
    expect(toneFor("missing")).toBe("danger");
    expect(toneFor("weak")).toBe("warning");
    expect(toneFor("unknown-status")).toBe("neutral");
  });
});
