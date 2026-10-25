"""Line-by-line ports of bench_press's quantile functions (`lib/src/stats/fieller.dart` at 5fd6396).

bench_press approximates Student's t quantile (Hill 1970, Algorithm 396) instead of computing it
exactly. The ports exist so `current_rule` reproduces bench_press's verdicts bit for bit; our own
intervals use exact quantiles from scipy.
"""

import math

_LANCZOS_G = 7
_LANCZOS = (
    0.99999999999980993,
    676.5203681218851,
    -1259.1392167224028,
    771.32342877765313,
    -176.61502916214059,
    12.507343278686905,
    -0.13857109526572012,
    9.9843695780195716e-6,
    1.5056327351493116e-7,
)

_ACKLAM_Q_LOW = 0.02425
_ACKLAM_Q_HIGH = 1.0 - _ACKLAM_Q_LOW
_ACKLAM_CENTRAL_NUM = (
    -3.969683028665376e01,
    2.209460984245205e02,
    -2.759285104469687e02,
    1.383577518672690e02,
    -3.066479806614716e01,
    2.506628277459239e00,
)
_ACKLAM_CENTRAL_DEN = (
    -5.447609879822406e01,
    1.615858368580409e02,
    -1.556989798598866e02,
    6.680131188771972e01,
    -1.328068155288572e01,
)
_ACKLAM_TAIL_NUM = (
    -7.784894002430293e-03,
    -3.223964580411365e-01,
    -2.400758277161838e00,
    -2.549732539343734e00,
    4.374664141464968e00,
    2.938163982698783e00,
)
_ACKLAM_TAIL_DEN = (
    7.784695709041462e-03,
    3.224671290700398e-01,
    2.445134137142996e00,
    3.754408661907416e00,
)


def student_t_quantile(p: float, df: float) -> float:
    """bench_press `studentTQuantile`: upper quantile p in (0.5, 1) of Student's t."""
    if p <= 0.5 or p >= 1.0:
        raise ValueError(f"p must be in (0.5, 1.0) for the upper tail, got {p}")
    df = 1.0 if df < 1.0 else df
    if df == 1.0:
        return math.tan(math.pi * (p - 0.5))
    if df == 2.0:
        alpha = 2.0 * (1.0 - p)
        return math.sqrt(2.0 / (alpha * (2.0 - alpha)) - 2.0)
    if df < 2.0:
        return _student_t_quantile_small_df(p, df)
    return _student_t_quantile_hill(p, df)


def _student_t_quantile_small_df(p: float, df: float) -> float:
    low = student_t_quantile(p, 2.0)
    high = student_t_quantile(p, 1.0)
    for _ in range(45):
        mid = (low + high) / 2.0
        if mid <= 0.0:
            cdf = 0.5
        else:
            cdf = 1.0 - 0.5 * _regularized_incomplete_beta(df / (df + mid * mid), df / 2.0, 0.5)
        if cdf < p:
            low = mid
        else:
            high = mid
    return (low + high) / 2.0


def _student_t_quantile_hill(p: float, n: float) -> float:
    two_tail_p = 2.0 * (1.0 - p)
    a = 1.0 / (n - 0.5)
    b = 48.0 / (a * a)
    c = ((20700.0 * a / b - 98.0) * a - 16.0) * a + 96.36
    d = ((94.5 / (b + c) - 3.0) / b + 1.0) * math.sqrt(a * math.pi / 2.0) * n
    x = d * two_tail_p
    y = math.pow(x, 2.0 / n)

    if y > 0.05 + a:
        x = normal_quantile(p)
        y = x * x
        if n < 5.0:
            c += 0.3 * (n - 4.5) * (x + 0.6)
        c = (((0.05 * d * x - 5.0) * x - 7.0) * x - 2.0) * x + b + c
        y = (((((0.4 * y + 6.3) * y + 36.0) * y + 94.5) / c - y - 3.0) / b + 1.0) * x
        y = a * y * y
        y = math.exp(y) - 1.0 if y > 0.002 else 0.5 * y * y + y
    else:
        y = (
            (1.0 / (((n + 6.0) / (n * y) - 0.089 * d - 0.822) * (n + 2.0) * 3.0) + 0.5 / (n + 4.0)) * y
            - 1.0
        ) * (n + 1.0) / (n + 2.0) + 1.0 / y

    return math.sqrt(n * y)


def _log_gamma(z: float) -> float:
    if z < 0.5:
        return math.log(math.pi / math.sin(math.pi * z)) - _log_gamma(1.0 - z)
    z_minus_1 = z - 1.0
    x = _LANCZOS[0]
    for i in range(1, _LANCZOS_G + 2):
        x += _LANCZOS[i] / (z_minus_1 + i)
    t = z_minus_1 + _LANCZOS_G + 0.5
    return 0.5 * math.log(2.0 * math.pi) + (z_minus_1 + 0.5) * math.log(t) - t + math.log(x)


def _clamp_tiny(val: float) -> float:
    return 1e-30 if abs(val) < 1e-30 else val


def _regularized_incomplete_beta(x: float, a: float, b: float) -> float:
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    if x > (a + 1.0) / (a + b + 2.0):
        return 1.0 - _regularized_incomplete_beta(1.0 - x, b, a)

    log_beta = _log_gamma(a) + _log_gamma(b) - _log_gamma(a + b)
    front = math.exp(a * math.log(x) + b * math.log(1.0 - x) - log_beta) / a

    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 / _clamp_tiny(1.0 - qab * x / qap)
    h = d
    for m in range(1, 201):
        m2 = 2 * m
        aa_even = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 / _clamp_tiny(1.0 + aa_even * d)
        c = _clamp_tiny(1.0 + aa_even / c)
        h *= d * c

        aa_odd = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 / _clamp_tiny(1.0 + aa_odd * d)
        c = _clamp_tiny(1.0 + aa_odd / c)
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 3e-14:
            break
    return front * h


def normal_quantile(p: float) -> float:
    """bench_press `normalQuantile` (Acklam's rational approximation)."""
    if p <= 0.0 or p >= 1.0:
        raise ValueError(f"p must be strictly in (0, 1), got {p}")
    if p < _ACKLAM_Q_LOW:
        return _eval_acklam_tail(math.sqrt(-2.0 * math.log(p)))
    if p <= _ACKLAM_Q_HIGH:
        q = p - 0.5
        r = q * q
        n, d = _ACKLAM_CENTRAL_NUM, _ACKLAM_CENTRAL_DEN
        return (
            (((((n[0] * r + n[1]) * r + n[2]) * r + n[3]) * r + n[4]) * r + n[5])
            * q
            / (((((d[0] * r + d[1]) * r + d[2]) * r + d[3]) * r + d[4]) * r + 1.0)
        )
    return -_eval_acklam_tail(math.sqrt(-2.0 * math.log(1.0 - p)))


def _eval_acklam_tail(q: float) -> float:
    n, d = _ACKLAM_TAIL_NUM, _ACKLAM_TAIL_DEN
    return (((((n[0] * q + n[1]) * q + n[2]) * q + n[3]) * q + n[4]) * q + n[5]) / (
        (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0
    )
