"""Tests for the strategy sandbox (host driver + subprocess runner).

This is the code path that executes user-uploaded Python, so every failure
mode matters: timeouts, crashes, disallowed imports, and malformed output must
all surface as StrategyExecutionError (or a clean validation error) rather
than corrupting a run.
"""
import subprocess

import numpy as np
import pytest

from app.strategies.sandbox import (
    StrategyExecutionError,
    run_strategy,
    validate_strategy,
)


VALID_STRATEGY = """
STRATEGY_META = {
    "name": "test-strategy",
    "version": "1.0",
    "role": "challenger",
    "required_inputs": ["score"],
    "params": {"cutoff": {"type": "float", "default": 0.30}},
}

def score(features, params):
    s = features["score"]
    return (s - s.min()) / (s.max() - s.min() + 1e-9)

def approve(features, pd_hat, params):
    return pd_hat < params.get("cutoff", 0.30)
"""


def _features(n=200, seed=0):
    rng = np.random.default_rng(seed)
    return {"score": rng.uniform(580.0, 800.0, n)}


# ---------------------------------------------------------------------------
# run_strategy
# ---------------------------------------------------------------------------

class TestRunStrategy:
    def test_happy_path_returns_pd_hat_and_mask(self):
        feats = _features()
        pd_hat, mask = run_strategy(VALID_STRATEGY, feats, {"cutoff": 0.30})
        assert len(pd_hat) == len(mask) == 200
        assert pd_hat.dtype == np.float64
        assert mask.dtype == np.bool_
        assert 0 < mask.sum() < 200

    def test_params_are_passed_through(self):
        feats = _features()
        _, strict = run_strategy(VALID_STRATEGY, feats, {"cutoff": 0.10})
        _, loose = run_strategy(VALID_STRATEGY, feats, {"cutoff": 0.90})
        assert strict.sum() < loose.sum()

    def test_pd_hat_is_clipped_to_unit_interval(self):
        code = """
def score(features, params):
    return features["score"] * 100.0 - 50.0

def approve(features, pd_hat, params):
    return pd_hat > 0.5
"""
        pd_hat, _ = run_strategy(code, _features(), {})
        assert pd_hat.min() >= 0.0
        assert pd_hat.max() <= 1.0

    def test_allowed_import_numpy_works(self):
        code = """
import numpy as np

def score(features, params):
    return np.clip(features["score"] / 1000.0, 0, 1)

def approve(features, pd_hat, params):
    return np.ones_like(pd_hat, dtype=bool)
"""
        pd_hat, mask = run_strategy(code, _features(), {})
        assert mask.all()
        assert len(pd_hat) == 200

    def test_disallowed_top_level_import_is_blocked(self):
        code = "import os\n" + VALID_STRATEGY
        with pytest.raises(StrategyExecutionError, match="not allowed"):
            run_strategy(code, _features(), {})

    def test_disallowed_import_inside_function_is_blocked(self):
        code = """
def score(features, params):
    import subprocess
    return features["score"] * 0

def approve(features, pd_hat, params):
    return pd_hat > 0
"""
        with pytest.raises(StrategyExecutionError, match="not allowed"):
            run_strategy(code, _features(), {})

    def test_timeout_kills_runaway_strategy(self):
        code = """
def score(features, params):
    while True:
        pass

def approve(features, pd_hat, params):
    return pd_hat > 0
"""
        with pytest.raises(StrategyExecutionError, match="timed out"):
            run_strategy(code, _features(), {}, timeout=2.0)

    def test_code_that_fails_to_load_reports_error(self):
        code = "raise RuntimeError('boom at import time')"
        with pytest.raises(StrategyExecutionError, match="failed to load"):
            run_strategy(code, _features(), {})

    def test_score_exception_is_reported(self):
        code = """
def score(features, params):
    raise ValueError("bad score input")

def approve(features, pd_hat, params):
    return pd_hat > 0
"""
        with pytest.raises(StrategyExecutionError, match=r"score\(\) raised"):
            run_strategy(code, _features(), {})

    def test_approve_exception_is_reported(self):
        code = """
def score(features, params):
    return features["score"] * 0.0

def approve(features, pd_hat, params):
    raise KeyError("missing column")
"""
        with pytest.raises(StrategyExecutionError, match=r"approve\(\) raised"):
            run_strategy(code, _features(), {})

    def test_missing_score_or_approve_is_reported(self):
        code = "X = 1\n"
        with pytest.raises(StrategyExecutionError, match="must define callable"):
            run_strategy(code, _features(), {})

    def test_non_callable_score_is_reported(self):
        code = """
score = 5

def approve(features, pd_hat, params):
    return pd_hat > 0
"""
        with pytest.raises(StrategyExecutionError, match="must define callable"):
            run_strategy(code, _features(), {})

    def test_output_length_mismatch_is_reported(self):
        code = """
def score(features, params):
    return [0.5]

def approve(features, pd_hat, params):
    return [True]
"""
        with pytest.raises(StrategyExecutionError, match="length mismatch"):
            run_strategy(code, _features(), {})

    def test_unparseable_subprocess_stdout_is_reported(self, monkeypatch):
        fake = subprocess.CompletedProcess(args=[], returncode=0,
                                           stdout=b"not an npz archive", stderr=b"")
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: fake)
        with pytest.raises(StrategyExecutionError, match="could not parse"):
            run_strategy(VALID_STRATEGY, _features(), {})

    def test_non_json_stderr_is_passed_through_verbatim(self, monkeypatch):
        fake = subprocess.CompletedProcess(args=[], returncode=1,
                                           stdout=b"", stderr=b"segfault-ish garbage")
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: fake)
        with pytest.raises(StrategyExecutionError, match="segfault-ish garbage"):
            run_strategy(VALID_STRATEGY, _features(), {})


# ---------------------------------------------------------------------------
# validate_strategy
# ---------------------------------------------------------------------------

class TestValidateStrategy:
    def test_valid_strategy_passes_with_sample_metrics(self):
        out = validate_strategy(VALID_STRATEGY)
        assert out["ok"] is True
        assert out["error"] is None
        assert out["meta"]["name"] == "test-strategy"
        sm = out["sample_metrics"]
        assert sm["n"] == 100
        assert 0.0 <= sm["approval_rate"] <= 1.0
        assert 0.0 <= sm["pd_hat_min"] <= sm["pd_hat_max"] <= 1.0

    def test_syntax_error_is_rejected(self):
        out = validate_strategy("def score(:\n")
        assert out["ok"] is False
        assert "syntax error" in out["error"]

    def test_missing_meta_keys_are_listed(self):
        code = """
STRATEGY_META = {"name": "x"}

def score(features, params):
    return features["score"] * 0

def approve(features, pd_hat, params):
    return pd_hat > 0
"""
        out = validate_strategy(code)
        assert out["ok"] is False
        assert "missing" in out["error"]
        for key in ("required_inputs", "role", "version", "params"):
            assert key in out["error"]

    def test_missing_meta_entirely_is_rejected(self):
        code = """
def score(features, params):
    return features["score"] * 0

def approve(features, pd_hat, params):
    return pd_hat > 0
"""
        out = validate_strategy(code)
        assert out["ok"] is False
        assert "STRATEGY_META" in out["error"]

    def test_required_inputs_must_be_a_list(self):
        code = """
STRATEGY_META = {
    "name": "x", "version": "1", "role": "challenger",
    "required_inputs": "score", "params": {},
}

def score(features, params):
    return features["score"] * 0

def approve(features, pd_hat, params):
    return pd_hat > 0
"""
        out = validate_strategy(code)
        assert out["ok"] is False
        assert "must be a list" in out["error"]

    def test_missing_approve_function_is_rejected(self):
        code = """
STRATEGY_META = {
    "name": "x", "version": "1", "role": "challenger",
    "required_inputs": ["score"], "params": {},
}

def score(features, params):
    return features["score"] * 0
"""
        out = validate_strategy(code)
        assert out["ok"] is False
        assert "score(...) and approve(...)" in out["error"]

    def test_trial_run_failure_is_reported(self):
        code = """
STRATEGY_META = {
    "name": "x", "version": "1", "role": "challenger",
    "required_inputs": ["score"], "params": {},
}

def score(features, params):
    raise RuntimeError("always fails")

def approve(features, pd_hat, params):
    return pd_hat > 0
"""
        out = validate_strategy(code)
        assert out["ok"] is False
        assert "always fails" in out["error"]

    def test_meta_that_cannot_be_evaluated_statically_is_rejected(self):
        code = """
STRATEGY_META = build_meta()

def score(features, params):
    return features["score"] * 0

def approve(features, pd_hat, params):
    return pd_hat > 0
"""
        out = validate_strategy(code)
        assert out["ok"] is False
