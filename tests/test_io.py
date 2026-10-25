import json

import numpy as np
import pytest

from bench_stats.io import load_run


def test_load_suite_fixture(suite_path):
    run = load_run(suite_path)
    recs = run.by_key()
    assert set(recs) == {"single:aot", "multi:aot", "unstable:aot", "base:aot:group=G", "fast:aot:group=G"}

    single = recs["single:aot"]
    assert single.processes == 1
    assert single.bench_press_samples() == list(single.raw_trials_ns)
    assert len(single.raw_trials_ns) == 16

    multi = recs["multi:aot"]
    assert multi.processes == 4
    assert multi.bench_press_samples() == list(multi.process_means_ns)
    np.testing.assert_allclose(multi.process_values(), multi.process_means_ns, rtol=1e-12)
    assert multi.upstream_components["processes"] == 4

    unstable = recs["unstable:aot"]
    assert not unstable.is_stable and unstable.warmup_stable is False

    base = recs["base:aot:group=G"]
    assert base.group == "G" and base.processes == 3


def test_median_reduction(suite_path):
    rec = load_run(suite_path).by_key()["multi:aot"]
    np.testing.assert_allclose(rec.process_values("median"), [np.median(t) for t in rec.process_trials])


def test_rejects_unknown_schema(tmp_path, suite_path):
    data = json.loads(suite_path.read_text())
    data["version"] = 2
    path = tmp_path / "run.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="schema version 2"):
        load_run(path)
