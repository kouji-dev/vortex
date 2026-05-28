"""Per-task cost accumulator + budget breach detector.

Costs are stored in *cents* (integers) throughout. Floating-point math is
deliberately avoided so the same number can be summed across many events
without drift.

Buckets:
- ``llm_cents``       — tokens spent via Gateway
- ``sandbox_cents``   — wall-clock minutes × per-minute rate
- ``storage_cents``   — MB-days × per-MB-day rate

The tracker emits one :class:`BudgetBreach` per crossed threshold (50/80/100%
configurable). It will only fire each threshold *once* per task lifetime.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field


class CostBucket(str, enum.Enum):
    llm = "llm"
    sandbox = "sandbox"
    storage = "storage"


@dataclass
class Budget:
    """Pool budget cap.

    ``cents`` — hard cap; the breach at 100% pauses the run.
    ``warn_thresholds_pct`` — soft warnings emitted (default 50% and 80%).
    """

    cents: int
    warn_thresholds_pct: tuple[int, ...] = (50, 80)

    def __post_init__(self) -> None:
        if self.cents < 0:
            raise ValueError("budget must be non-negative")


@dataclass(frozen=True)
class BudgetBreach:
    """Emitted when a threshold is crossed."""

    threshold_pct: int
    total_cents: int
    budget_cents: int
    is_hard_cap: bool


@dataclass
class CostTracker:
    """Accumulator for one task / run.

    Call :meth:`add` for each cost delta. Each call returns the list of
    threshold breaches triggered by this delta. Past breaches are not
    re-emitted.
    """

    budget: Budget
    spend: dict[CostBucket, int] = field(default_factory=dict)
    _fired: set[int] = field(default_factory=set)

    @property
    def total_cents(self) -> int:
        return sum(self.spend.values())

    @property
    def remaining_cents(self) -> int:
        return max(0, self.budget.cents - self.total_cents)

    def add(self, bucket: CostBucket, delta_cents: int) -> list[BudgetBreach]:
        if delta_cents < 0:
            raise ValueError("delta_cents must be non-negative")
        self.spend[bucket] = self.spend.get(bucket, 0) + delta_cents
        return self._collect_breaches()

    def add_llm(self, cents: int) -> list[BudgetBreach]:
        return self.add(CostBucket.llm, cents)

    def add_sandbox_minutes(self, minutes: float, cents_per_minute: int) -> list[BudgetBreach]:
        cents = int(round(minutes * cents_per_minute))
        return self.add(CostBucket.sandbox, max(0, cents))

    def add_storage_mb_days(
        self, mb_days: float, cents_per_mb_day: int
    ) -> list[BudgetBreach]:
        cents = int(round(mb_days * cents_per_mb_day))
        return self.add(CostBucket.storage, max(0, cents))

    def _collect_breaches(self) -> list[BudgetBreach]:
        if self.budget.cents == 0:
            # No cap configured — never breach.
            return []
        pct = (self.total_cents * 100) // self.budget.cents
        breaches: list[BudgetBreach] = []
        # warn thresholds (in ascending order, deduped)
        for thr in sorted(set(self.budget.warn_thresholds_pct)):
            if thr <= 0 or thr >= 100:
                continue
            if pct >= thr and thr not in self._fired:
                self._fired.add(thr)
                breaches.append(
                    BudgetBreach(
                        threshold_pct=thr,
                        total_cents=self.total_cents,
                        budget_cents=self.budget.cents,
                        is_hard_cap=False,
                    )
                )
        if pct >= 100 and 100 not in self._fired:
            self._fired.add(100)
            breaches.append(
                BudgetBreach(
                    threshold_pct=100,
                    total_cents=self.total_cents,
                    budget_cents=self.budget.cents,
                    is_hard_cap=True,
                )
            )
        return breaches

    def is_over_budget(self) -> bool:
        return self.budget.cents > 0 and self.total_cents >= self.budget.cents
