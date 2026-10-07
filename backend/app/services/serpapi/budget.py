"""Per-run call cap: `SERP_BUDGET_PER_ANALYSIS` (12) or `SERP_BUDGET_PER_INVESTIGATION` (8).

Counts only credit-spending (live) calls. Cache hits are free and never count, which matches
`analyses.serp_calls_used` (API.md: planned 11, cached 4, new 7 -> used 7).
"""


class RunBudgetExhausted(Exception):
    """The run has spent its live-call cap. Collection stops cleanly (warning, no failure)."""

    def __init__(self, cap: int) -> None:
        super().__init__(f"run budget of {cap} live SerpApi calls is exhausted")
        self.cap = cap


class RunBudget:
    def __init__(self, cap: int) -> None:
        if cap < 0:
            raise ValueError("cap must be >= 0")
        self._cap = cap
        self._spent = 0

    @property
    def cap(self) -> int:
        return self._cap

    @property
    def spent(self) -> int:
        return self._spent

    @property
    def remaining(self) -> int:
        return self._cap - self._spent

    def check(self, calls: int = 1) -> None:
        if self._spent + calls > self._cap:
            raise RunBudgetExhausted(self._cap)

    def consume(self, calls: int = 1) -> None:
        self.check(calls)
        self._spent += calls
