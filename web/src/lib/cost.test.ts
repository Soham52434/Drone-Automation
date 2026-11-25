import { describe, expect, it } from "vitest";

import { costBadge, formatTokens, formatUsd, quotaShare } from "./cost";

describe("cost formatting", () => {
  it("keeps tiny dollar amounts readable", () => {
    expect(formatUsd(0)).toBe("$0.00");
    expect(formatUsd(0.00002)).toBe("<$0.0001");
    expect(formatUsd(0.0042)).toBe("$0.0042");
    expect(formatUsd(0.25)).toBe("$0.250");
    expect(formatUsd(3.5)).toBe("$3.50");
  });

  it("shortens token counts", () => {
    expect(formatTokens(950)).toBe("950");
    expect(formatTokens(4_200)).toBe("4.2K");
    expect(formatTokens(48_000)).toBe("48K");
    expect(formatTokens(2_500_000)).toBe("2.50M");
  });

  it("shares free-tier use and caps at the limit", () => {
    expect(quotaShare(1_440, 14_400)).toBeCloseTo(0.1);
    expect(quotaShare(30_000, 14_400)).toBe(1);
    expect(quotaShare(5, null)).toBeNull();
  });

  it("labels the button", () => {
    expect(costBadge(null)).toBe("Cost");
    const empty = { requests: 0, failed: 0, input_tokens: 0, output_tokens: 0, usd: 0, by_job: [], by_model: [], quotas: [] };
    expect(costBadge(empty)).toBe("$0.00");
    expect(costBadge({ ...empty, requests: 3, usd: 0.0031 })).toBe("$0.0031");
  });
});
