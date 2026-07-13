/**
 * A spend would exceed a configured budget cap (org / team / member scope).
 * Thrown by budget enforcement; mapped to 402/429-style responses upstream.
 */
export class BudgetExceededError extends Error {
  constructor(
    /** Which budget tripped: "org" | "team" | "member". */
    readonly scope: string,
    /** The configured cap, in micro-USD. */
    readonly limitMicro: number,
    /** Spend already accrued against the cap, in micro-USD. */
    readonly spentMicro: number,
  ) {
    super(
      `budget exceeded (${scope}): spent ${spentMicro} of ${limitMicro} micro-USD`,
    );
    this.name = "BudgetExceededError";
  }
}

/** Managed-mode credit wallet is empty (or would go negative). */
export class CreditExhaustedError extends Error {
  constructor(
    /** Current wallet balance, in micro-USD. */
    readonly balanceMicro: number,
  ) {
    super(`credits exhausted: balance ${balanceMicro} micro-USD`);
    this.name = "CreditExhaustedError";
  }
}
