"""Subprocess entry point that executes an untrusted user strategy.

THREAT MODEL
------------
This is a defence-in-depth sandbox for code the platform did not write —
including, once the authoring agent lands, code a language model wrote. It is
not a container: a determined attacker with a CPython zero-day is out of
scope. What it does close:

  process     a separate process, so a crash or segfault cannot take the API
              down, and a hard wall-clock timeout kills a hang
  cpu/memory  RLIMIT_CPU and RLIMIT_AS bound runaway loops and allocations
  filesystem  builtins.open raises once the features are loaded, so the
              library paths that write files (np.save, np.savetxt, pandas
              to_csv) fail too — not just a literal open() in the source.
              RLIMIT_FSIZE caps anything that slips past at 4 MiB, bounding
              disk abuse. Note that reading is what actually leaks: a
              strategy that could read a file could encode it into the float
              array it returns, and no rlimit stops that — which is why the
              source gate refuses reads outright
  network     socket.socket raises; no module that could restore it is
              reachable
  builtins    the strategy executes against an explicit allowlist dict, not
              the real builtins module, so open/eval/exec/compile/__import__
              are simply absent
  imports     the guarded __import__ in that dict admits a numeric allowlist
  syntax      the host AST-gates the source first (see sandbox.py), rejecting
              dunder attribute access, which is how every "restricted
              builtins" bypass starts

Before this, an uploaded strategy could call open() and read backend/.env.

Protocol:
  stdin  : JSON {"code": str, "params": dict, "features_path": str}
  stdout : np.savez archive (binary) with arrays {pd_hat, approve_mask}
  stderr : on failure, a JSON error object; exit code is non-zero.
"""
from __future__ import annotations

import io
import json
import sys

_IMPORT_WHITELIST = {
    "numpy", "pandas", "math", "statistics", "scipy", "itertools",
    "functools", "collections",
}

# Everything the strategy contract plausibly needs, and nothing that reaches
# the filesystem, the interpreter, or code execution. Deliberately omitted:
# open, eval, exec, compile, __import__ (replaced below), input, breakpoint,
# globals, locals, vars, dir, getattr, setattr, delattr, help, memoryview —
# the ones that execute code or read a namespace by string.
_SAFE_BUILTIN_NAMES = {
    "abs", "all", "any", "bool", "bytes", "callable", "chr", "complex",
    "dict", "divmod", "enumerate", "filter", "float", "format", "frozenset",
    "hash", "hex", "int", "isinstance", "issubclass", "iter", "len", "list",
    "map", "max", "min", "next", "oct", "ord", "pow", "print", "range",
    "repr", "reversed", "round", "set", "slice", "sorted", "str", "sum",
    "tuple", "zip", "type", "object", "super", "classmethod", "staticmethod",
    "property", "bytearray", "id",
    # exceptions a strategy may legitimately raise or catch
    "ArithmeticError", "AssertionError", "AttributeError", "Exception",
    "IndexError", "KeyError", "LookupError", "NotImplementedError",
    "OverflowError", "RuntimeError", "StopIteration", "TypeError",
    "ValueError", "ZeroDivisionError",
    "True", "False", "None",
}


def _safe_builtins() -> dict:
    import builtins

    real_import = builtins.__import__

    def _guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        root = name.split(".")[0]
        if root not in _IMPORT_WHITELIST:
            raise ImportError(f"import of '{name}' is not allowed in the strategy sandbox")
        return real_import(name, globals, locals, fromlist, level)

    ns = {n: getattr(builtins, n) for n in _SAFE_BUILTIN_NAMES if hasattr(builtins, n)}
    ns["__import__"] = _guarded_import
    return ns


def _install_guards() -> None:
    """Apply the process-wide limits. Called after numpy and the feature file
    are loaded, so the limits never fight the platform's own setup."""
    import builtins
    import resource
    import socket

    def _limit(what, soft, hard):
        try:
            resource.setrlimit(what, (soft, hard))
        except (ValueError, OSError):
            pass

    _limit(resource.RLIMIT_CPU, 6, 10)
    _limit(resource.RLIMIT_AS, 1024 * 1024 * 1024, 1024 * 1024 * 1024)
    # Backstop against disk abuse by anything that reaches a file some other
    # way. Generous enough that an allowlisted library importing lazily
    # (scipy writes temp files on import) still works.
    _limit(resource.RLIMIT_FSIZE, 4 * 1024 * 1024, 4 * 1024 * 1024)

    # The strategy's own namespace has no open(), but library code does:
    # np.save calls the builtin. Closing it here covers both.
    def _no_open(*_a, **_k):
        raise PermissionError("file access is disabled in the strategy sandbox")

    builtins.open = _no_open  # type: ignore[assignment]

    def _no_socket(*_a, **_k):
        raise PermissionError("network access is disabled in the strategy sandbox")

    socket.socket = _no_socket  # type: ignore[assignment]


def _fail(message: str) -> None:
    sys.stderr.write(json.dumps({"error": message}))
    sys.stderr.flush()
    sys.exit(1)


def main() -> None:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw)
        code = payload["code"]
        params = payload.get("params") or {}
        features_path = payload["features_path"]
    except Exception as exc:  # noqa: BLE001
        _fail(f"bad payload: {exc}")
        return

    # numpy must be imported before the guards (it imports submodules lazily
    # and touches the filesystem while doing so).
    import numpy as np

    try:
        loaded = np.load(features_path, allow_pickle=False)
        features = {k: loaded[k] for k in loaded.files}
    except Exception as exc:  # noqa: BLE001
        _fail(f"failed to load features: {exc}")
        return

    _install_guards()

    ns: dict = {"__builtins__": _safe_builtins(), "__name__": "strategy"}
    try:
        exec(compile(code, "<strategy>", "exec"), ns)
    except Exception as exc:  # noqa: BLE001
        _fail(f"strategy code failed to load: {type(exc).__name__}: {exc}")
        return

    score_fn = ns.get("score")
    approve_fn = ns.get("approve")
    if not callable(score_fn) or not callable(approve_fn):
        _fail("strategy must define callable score(...) and approve(...)")
        return

    try:
        pd_hat = np.asarray(score_fn(features, params), dtype=np.float64).ravel()
        pd_hat = np.clip(pd_hat, 0.0, 1.0)
    except Exception as exc:  # noqa: BLE001
        _fail(f"score() raised: {type(exc).__name__}: {exc}")
        return

    try:
        approve_mask = np.asarray(approve_fn(features, pd_hat, params)).ravel().astype(bool)
    except Exception as exc:  # noqa: BLE001
        _fail(f"approve() raised: {type(exc).__name__}: {exc}")
        return

    n = len(next(iter(features.values()))) if features else len(pd_hat)
    if len(pd_hat) != n or len(approve_mask) != n:
        _fail(f"output length mismatch: expected {n}, got pd_hat={len(pd_hat)} mask={len(approve_mask)}")
        return

    buf = io.BytesIO()
    np.savez(buf, pd_hat=pd_hat, approve_mask=approve_mask)
    sys.stdout.buffer.write(buf.getvalue())
    sys.stdout.buffer.flush()


if __name__ == "__main__":
    main()
