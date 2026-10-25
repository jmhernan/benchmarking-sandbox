import json
import math
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
BENCH_PRESS_COMMIT = "5fd6396"


def decode(x):
    """Undo the golden generator's encoding of non-finite doubles as strings."""
    if isinstance(x, str):
        return {"Infinity": math.inf, "-Infinity": -math.inf, "NaN": math.nan}[x]
    return float(x)


@pytest.fixture(scope="session")
def golden():
    return json.loads((FIXTURES / f"bench_press_golden_{BENCH_PRESS_COMMIT}.json").read_text())


@pytest.fixture(scope="session")
def suite_path():
    return FIXTURES / f"bench_press_suite_{BENCH_PRESS_COMMIT}.json"
