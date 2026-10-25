"""Interval result type shared by the ratio estimators."""

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class RatioInterval:
    """Confidence interval for a speedup ratio (baseline / candidate; > 1 means the candidate is faster).

    `estimand` names what the ratio compares, e.g. arithmetic means of per-process means
    (Fieller) or geometric means (log-scale estimators).
    """

    method: str
    estimand: str
    ratio: float
    lower: float
    upper: float
    conf: float
    df: float
    is_valid: bool
    p_value: float = math.nan
    g: float = math.nan
    paired: bool = False

    @property
    def bounded(self) -> bool:
        return self.is_valid and math.isfinite(self.lower) and math.isfinite(self.upper)

    @property
    def excludes_one(self) -> bool:
        return self.bounded and not (self.lower <= 1.0 <= self.upper)

    @property
    def relative_half_width(self) -> float:
        """Half the width of the interval on the log scale, as a fraction (0.01 = ±1%)."""
        if not self.bounded or self.lower <= 0:
            return math.inf
        return 0.5 * (math.log(self.upper) - math.log(self.lower))
