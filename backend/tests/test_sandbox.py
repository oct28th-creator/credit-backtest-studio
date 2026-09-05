"""Strategy sandbox: what uploaded code may and may not do.

Before this suite the sandbox let a strategy call open() — it could read
backend/.env, where the API key lives, and encode it into the float array it
returns. These tests pin each escape shut. They are written as the attacks
themselves, because a sandbox test that only checks the happy path tests
nothing.
"""
import os

import numpy as np
import pytest

from app.strategies.sandbox import (
    StrategyExecutionError, StrategyRejected, gate_source, run_strategy,
    validate_strategy,
)

META = ('STRATEGY_META = {"name":"p","version":"1","role":"challenger",'
        '"required_inputs":["score"],"params":{}}')


def _strategy(body: str) -> str:
    """A syntactically valid strategy whose score() runs ``body``."""
    return f"""
import numpy as np
{META}
def score(features, params):
{body}
    return np.zeros(len(features['score']))
def approve(features, pd_hat, params):
    return np.ones(len(pd_hat), dtype=bool)
"""


def _run(code):
    return run_strategy(code, {"score": np.zeros(5)}, {})


# --------------------------------------------------------------------------- #
# The escapes
# --------------------------------------------------------------------------- #
class TestEscapesAreClosed:
    def test_reading_a_file_is_rejected(self):
        """The one that mattered: backend/.env holds the API key."""
        with pytest.raises(StrategyRejected, match="open"):
            _run(_strategy("    data = open('/etc/hostname').read()"))

    def test_writing_a_file_is_rejected(self):
        with pytest.raises(StrategyRejected, match="open"):
            _run(_strategy("    open('/tmp/sandbox_test_pwned','w').write('x')"))

    def test_subclasses_walk_is_rejected(self):
        """().__class__.__base__.__subclasses__() is how every restricted-
        builtins bypass starts."""
        with pytest.raises(StrategyRejected, match="__subclasses__|__class__"):
            _run(_strategy("    cs = ().__class__.__base__.__subclasses__()"))

    def test_function_globals_walk_is_rejected(self):
        with pytest.raises(StrategyRejected, match="__globals__"):
            _run(_strategy("    g = np.mean.__globals__"))

    @pytest.mark.parametrize("call", ["eval('1+1')", "exec('x=1')", "compile('1','','eval')"])
    def test_code_execution_builtins_are_rejected(self, call):
        with pytest.raises(StrategyRejected):
            _run(_strategy(f"    r = {call}"))

    @pytest.mark.parametrize("call", [
        "getattr(np, 'load')", "vars(np)", "globals()", "locals()", "dir(np)",
    ])
    def test_namespace_readers_are_rejected(self, call):
        """getattr(obj, "__class__") is the attribute gate spelled as a string."""
        with pytest.raises(StrategyRejected):
            _run(_strategy(f"    r = {call}"))

    @pytest.mark.parametrize("stmt", [
        "import os", "import subprocess", "import sys", "from os import path",
        "import socket", "import importlib",
    ])
    def test_dangerous_imports_are_rejected_at_upload_time(self, stmt):
        code = f"""
import numpy as np
{stmt}
{META}
def score(features, params):
    return np.zeros(len(features['score']))
def approve(features, pd_hat, params):
    return np.ones(len(pd_hat), dtype=bool)
"""
        with pytest.raises(StrategyRejected, match="import"):
            _run(code)

    def test_the_rejection_names_the_line(self):
        """An upload-time error a person can act on beats a runtime one."""
        with pytest.raises(StrategyRejected, match="line 5"):
            _run(_strategy("    r = open('/etc/hostname')"))


class TestRuntimeLimits:
    """Not everything can be caught statically — numpy will happily write a
    file with no forbidden name in sight."""

    def test_numpy_cannot_write_a_file(self, tmp_path):
        """The source gate cannot see this one — there is no forbidden name in
        `np.save(path, arr)`. builtins.open is closed in the child, and
        numpy's writer goes through it."""
        target = tmp_path / "exfil.npy"
        code = _strategy(f"    np.save(r'{target}', np.zeros(1000))")
        with pytest.raises(StrategyExecutionError, match="file access is disabled|PermissionError"):
            _run(code)
        assert not target.exists()

    def test_scipy_still_imports(self):
        """A blanket write ban broke scipy, which writes temp files on import.
        Allowlisted science libraries have to keep working or authors cannot
        write a real strategy."""
        code = _strategy("    import scipy.stats\n    _ = scipy.stats.norm.cdf(0.0)")
        pd_hat, _mask = _run(code)
        assert len(pd_hat) == 5

    def test_network_module_is_not_importable(self):
        code = _strategy("    import socket")
        with pytest.raises(StrategyRejected, match="import"):
            _run(code)

    def test_a_hang_is_killed(self):
        code = _strategy("    x = 0\n    while True:\n        x += 1")
        with pytest.raises(StrategyExecutionError, match="timed out|CPU|killed|failed"):
            run_strategy(code, {"score": np.zeros(5)}, {}, timeout=3.0)


# --------------------------------------------------------------------------- #
# Legitimate strategies keep working
# --------------------------------------------------------------------------- #
GOOD = """
import numpy as np
STRATEGY_META = {
    "name": "logistic", "version": "1.0", "role": "challenger",
    "required_inputs": ["score", "dti"],
    "params": {"cut": {"type": "number", "default": 0.5}},
}

def score(features, params):
    s = np.asarray(features['score'], dtype=float)
    d = np.asarray(features['dti'], dtype=float)
    return 1.0 / (1.0 + np.exp((s - 650) / 40.0 - d))

def approve(features, pd_hat, params):
    return pd_hat <= params.get('cut', 0.5)
"""


class TestLegitimateCode:
    def test_a_realistic_strategy_runs(self):
        feats = {"score": np.array([600., 650., 700., 720., 580.]),
                 "dti": np.array([0.3, 0.4, 0.2, 0.5, 0.6])}
        pd_hat, mask = run_strategy(GOOD, feats, {"cut": 0.5})
        assert len(pd_hat) == 5 and len(mask) == 5
        assert ((pd_hat >= 0) & (pd_hat <= 1)).all()
        assert mask.sum() > 0, "a sane cutoff should approve someone"

    def test_ordinary_builtins_remain_available(self):
        """type/isinstance/sorted are only dangerous through a dunder, and
        dunders are blocked — refusing them outright would just push authors
        into stranger code."""
        code = _strategy(
            "    assert isinstance(params, dict)\n"
            "    assert type(1) is int\n"
            "    assert sorted([3, 1, 2]) == [1, 2, 3]\n"
            "    assert sum(range(4)) == 6"
        )
        pd_hat, mask = _run(code)
        assert len(pd_hat) == 5

    def test_allowlisted_imports_work(self):
        code = _strategy("    import math\n    import scipy.stats\n    _ = math.sqrt(4)")
        pd_hat, _mask = _run(code)
        assert len(pd_hat) == 5

    def test_validate_accepts_a_good_strategy(self):
        out = validate_strategy(GOOD)
        assert out["ok"] is True
        assert out["meta"]["name"] == "logistic"
        assert out["sample_metrics"]["n"] == 100

    def test_validate_rejects_at_upload_with_a_readable_reason(self):
        out = validate_strategy(_strategy("    d = open('/etc/hostname').read()"))
        assert out["ok"] is False
        assert "open" in out["error"]


class TestSourceGate:
    def test_clean_source_has_no_violations(self):
        assert gate_source(GOOD) == []

    def test_syntax_error_is_reported_as_a_violation(self):
        assert gate_source("def score(:") != []

    def test_gate_reports_every_problem_not_just_the_first(self):
        bad = "import os\nx = eval('1')\ny = ().__class__\n"
        assert len(gate_source(bad)) >= 3
