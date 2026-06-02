"""Subprocess entry point that executes an untrusted user strategy.

THREAT MODEL (single-tenant demo grade, NOT a hardened multi-tenant sandbox):
  - Runs in a separate process so a crash/segfault cannot take down the API.
  - resource.setrlimit caps CPU time and address space to bound runaway code.
  - socket.socket is monkeypatched to deny all network access.
  - __import__ is restricted to a numeric/data-science allowlist, blocking os,
    subprocess, sys-level escapes via normal import. This is defence-in-depth,
    not a security boundary against a determined attacker (Python introspection
    can still reach builtins); it is adequate for a trusted-but-careless user
    uploading analytics code on a single-tenant demo deployment.

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


def _install_guards():
    import builtins
    import resource
    import socket

    # CPU and address-space limits.
    try:
        resource.setrlimit(resource.RLIMIT_CPU, (6, 10))
    except (ValueError, OSError):
        pass
    try:
        resource.setrlimit(resource.RLIMIT_AS, (1024 * 1024 * 1024, 1024 * 1024 * 1024))
    except (ValueError, OSError):
        pass

    # Capture the genuine callables BEFORE monkeypatching, so _restore can put
    # the real ones back (previously real_socket captured the _no_socket stub).
    real_socket = socket.socket
    real_import = builtins.__import__

    # Deny network.
    def _no_socket(*_a, **_k):
        raise PermissionError("network access is disabled in the strategy sandbox")

    socket.socket = _no_socket  # type: ignore[assignment]

    def _guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        root = name.split(".")[0]
        if root not in _IMPORT_WHITELIST:
            raise ImportError(f"import of '{name}' is not allowed in the strategy sandbox")
        return real_import(name, globals, locals, fromlist, level)

    builtins.__import__ = _guarded_import

    def _restore() -> None:
        builtins.__import__ = real_import
        socket.socket = real_socket  # type: ignore[assignment]

    return _restore


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

    # numpy must be imported before guards (it imports many submodules lazily).
    import numpy as np

    try:
        loaded = np.load(features_path, allow_pickle=False)
        features = {k: loaded[k] for k in loaded.files}
    except Exception as exc:  # noqa: BLE001
        _fail(f"failed to load features: {exc}")
        return

    restore = _install_guards()

    ns: dict = {"__builtins__": __builtins__}
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

    # Restore host-level imports so our own serialisation (np.savez -> zipfile)
    # is not blocked by the sandbox import allowlist.
    restore()

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
