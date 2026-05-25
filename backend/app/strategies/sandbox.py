"""Host-side driver for the strategy sandbox subprocess (see runner.py)."""
from __future__ import annotations

import ast
import io
import json
import os
import subprocess
import sys
import tempfile

import numpy as np

_RUNNER = os.path.join(os.path.dirname(__file__), "runner.py")

_REQUIRED_META_KEYS = {"name", "version", "role", "required_inputs", "params"}


class StrategyExecutionError(Exception):
    """Raised when a sandboxed strategy fails to run, times out, or is invalid."""


def run_strategy(
    code: str,
    features: dict[str, np.ndarray],
    params: dict,
    timeout: float = 15.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Execute ``code`` against ``features`` in a sandboxed subprocess.

    Returns (pd_hat, approve_mask). Raises StrategyExecutionError on failure or
    timeout.
    """
    feat_fd, feat_path = tempfile.mkstemp(suffix=".npz")
    os.close(feat_fd)
    try:
        np.savez(feat_path, **{k: np.asarray(v) for k, v in features.items()})
        payload = json.dumps({"code": code, "params": params or {}, "features_path": feat_path})
        try:
            proc = subprocess.run(
                [sys.executable, _RUNNER],
                input=payload.encode("utf-8"),
                capture_output=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise StrategyExecutionError(f"strategy timed out after {timeout}s") from exc

        if proc.returncode != 0:
            detail = proc.stderr.decode("utf-8", "replace").strip()
            try:
                detail = json.loads(detail).get("error", detail)
            except Exception:  # noqa: BLE001
                pass
            raise StrategyExecutionError(detail or "strategy subprocess failed")

        try:
            arr = np.load(io.BytesIO(proc.stdout), allow_pickle=False)
            pd_hat = np.asarray(arr["pd_hat"], dtype=np.float64)
            approve_mask = np.asarray(arr["approve_mask"], dtype=bool)
        except Exception as exc:  # noqa: BLE001
            raise StrategyExecutionError(f"could not parse strategy output: {exc}") from exc

        return pd_hat, approve_mask
    finally:
        try:
            os.unlink(feat_path)
        except OSError:
            pass


def _static_extract_meta(code: str) -> tuple[dict, set[str]]:
    """AST-parse the code to find STRATEGY_META and the set of top-level defs.

    Returns (meta_dict, defined_function_names). meta_dict may be {} if it could
    not be evaluated statically.
    """
    tree = ast.parse(code)
    func_names: set[str] = set()
    meta: dict = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            func_names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "STRATEGY_META":
                    try:
                        meta = ast.literal_eval(node.value)
                    except (ValueError, SyntaxError):
                        meta = {}
    return meta, func_names


def validate_strategy(code: str) -> dict:
    """Static + dynamic validation of an uploaded strategy.

    Checks the code parses, defines STRATEGY_META (with required keys), score and
    approve, then trial-runs it on a 100-row random sample in the sandbox.

    Returns {ok, meta, error, sample_metrics}.
    """
    # ── Static checks ────────────────────────────────────────────────────
    try:
        meta, funcs = _static_extract_meta(code)
    except SyntaxError as exc:
        return {"ok": False, "meta": {}, "error": f"syntax error: {exc}", "sample_metrics": None}

    if not isinstance(meta, dict) or not _REQUIRED_META_KEYS.issubset(meta.keys()):
        missing = _REQUIRED_META_KEYS - (set(meta.keys()) if isinstance(meta, dict) else set())
        return {
            "ok": False,
            "meta": meta if isinstance(meta, dict) else {},
            "error": f"STRATEGY_META missing or incomplete (missing keys: {sorted(missing)})",
            "sample_metrics": None,
        }
    if not isinstance(meta.get("required_inputs"), list):
        return {"ok": False, "meta": meta, "error": "STRATEGY_META['required_inputs'] must be a list",
                "sample_metrics": None}
    if "score" not in funcs or "approve" not in funcs:
        return {"ok": False, "meta": meta,
                "error": "strategy must define top-level score(...) and approve(...) functions",
                "sample_metrics": None}

    # ── Dynamic trial run on a 100-row sample ───────────────────────────
    rng = np.random.default_rng(0)
    n = 100
    features: dict[str, np.ndarray] = {}
    for name in meta["required_inputs"]:
        features[name] = rng.normal(0, 1, n)
    # Provide a plausible default 'outcome' too in case the strategy peeks.
    features.setdefault("bad", rng.integers(0, 2, n).astype(np.int8))

    params = {k: v.get("default") for k, v in (meta.get("params") or {}).items()
              if isinstance(v, dict)}

    try:
        pd_hat, approve_mask = run_strategy(code, features, params, timeout=15.0)
    except StrategyExecutionError as exc:
        return {"ok": False, "meta": meta, "error": str(exc), "sample_metrics": None}

    if len(pd_hat) != n or len(approve_mask) != n:
        return {"ok": False, "meta": meta,
                "error": f"trial output length mismatch (got pd_hat={len(pd_hat)}, mask={len(approve_mask)})",
                "sample_metrics": None}

    sample_metrics = {
        "n": n,
        "approval_rate": round(float(approve_mask.mean()), 4),
        "pd_hat_mean": round(float(pd_hat.mean()), 4),
        "pd_hat_min": round(float(pd_hat.min()), 4),
        "pd_hat_max": round(float(pd_hat.max()), 4),
    }
    return {"ok": True, "meta": meta, "error": None, "sample_metrics": sample_metrics}
