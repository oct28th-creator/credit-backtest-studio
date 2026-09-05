"""Run manifest — the reproducibility contract of a single experiment run.

Why this exists
---------------
Before this module a run was identified by ``snapshot_sha =
sha256(champion|challenger|beta|sample)``. That hash ignored the seed, the
strategy *code*, the dataset *content*, the policy overrides and the metric
version, so two runs with different numbers could share an id — fatal once an
agent starts generating hundreds of variations and citing them as evidence.

The manifest folds **everything that can change the numbers** into one
canonical JSON document. Its SHA-256 (``manifest_sha``) is the run's true
identity:

    same manifest_sha  =>  same metrics (bit-for-bit, same engine version)
    different metrics  =>  different manifest_sha

That property is what makes an agent-run experiment auditable and cacheable.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Optional

# Bump ENGINE_VERSION when the execution path changes in a way that can move
# the numbers; bump METRIC_VERSION when an L1-L5 definition changes. Both are
# part of the manifest, so old runs stay distinguishable from new ones.
ENGINE_VERSION = "1.1.0"
METRIC_VERSION = "l1-l5/2026.09"
GENERATOR_VERSION = "synthetic/1.0"

_HASH_CHUNK = 1 << 20  # 1 MiB


def canonical_json(obj: Any) -> str:
    """Deterministic JSON: sorted keys, no incidental whitespace."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, default=str)


def sha(obj: Any) -> str:
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


def _file_sha(path: str) -> str:
    h = hashlib.sha256()
    try:
        with Path(path).open("rb") as fh:
            for chunk in iter(lambda: fh.read(_HASH_CHUNK), b""):
                h.update(chunk)
    except OSError:
        return "unreadable"
    return h.hexdigest()


# --------------------------------------------------------------------------- #
# Fingerprints
# --------------------------------------------------------------------------- #
def strategy_fingerprint(ref: str, overrides: Optional[dict] = None) -> dict:
    """Identify a strategy by *content*, not by name.

    ``builtin:<id>`` hashes the strategy definition (cutoffs, gates, pricing)
    so editing a built-in strategy invalidates old run ids.
    ``custom:<id>`` hashes the uploaded source text.
    """
    from app.data.fixtures import STRATEGIES
    from app.db import repository

    kind, _, ident = ref.partition(":")
    if not ident:  # bare id, treat as built-in
        kind, ident = "builtin", ref

    if kind == "builtin":
        definition = STRATEGIES.get(ident, {})
        body = {"kind": "builtin", "id": ident, "definition_sha": sha(definition)}
    else:
        rec = repository.get_custom_strategy(ident)
        body = {
            "kind": "custom",
            "id": ident,
            "code_sha": hashlib.sha256((rec or {}).get("code_text", "").encode()).hexdigest(),
            "meta_sha": sha((rec or {}).get("meta", {})),
        }
    if overrides:
        body["overrides"] = dict(overrides)
    body["sha"] = sha(body)
    return body


def dataset_fingerprint(ref: str, seed: int = 42, n_rows: Optional[int] = None) -> dict:
    """Identify a dataset by content or by its generator inputs."""
    from app.data.fixtures import SAMPLES
    from app.db import repository

    kind, _, ident = ref.partition(":")
    if not ident:
        kind, ident = "builtin", ref

    if kind == "builtin":
        meta = next((s for s in SAMPLES if s["id"] == ident), None)
        rows = n_rows if n_rows is not None else min((meta or {}).get("n_rows", 50000), 80000)
        body = {
            "kind": "synthetic",
            "sample_id": ident,
            "n_rows": rows,
            "seed": seed,
            "generator": GENERATOR_VERSION,
        }
    else:
        rec = repository.get_custom_dataset(ident) or {}
        body = {
            "kind": "uploaded",
            "dataset_id": ident,
            "n_rows": rec.get("n_rows"),
            "columns": sorted(rec.get("columns", []) or []),
            "content_sha": _file_sha(rec["file_path"]) if rec.get("file_path") else "missing",
        }
    body["sha"] = sha(body)
    return body


# --------------------------------------------------------------------------- #
# Manifest
# --------------------------------------------------------------------------- #
def build_manifest(config: dict, *, parent_run_id: Optional[str] = None,
                   root_run_id: Optional[str] = None,
                   created_by: str = "user") -> dict:
    """Assemble the full manifest for a run configuration.

    ``config`` is an ``ExperimentConfig`` dump. ``created_by`` records who
    asked for the run ("user", "agent:<name>", "sweep:<id>") — the audit trail
    an agentic platform needs and a plain backtester does not.
    """
    dataset_ref = config.get("dataset_ref") or f"builtin:{config.get('sample_id')}"
    seed = int(config.get("seed", 42))
    policy = config.get("policy_overrides") or {}
    params = config.get("param_overrides") or {}

    roles: dict[str, Optional[str]] = {
        "champion": config.get("champion_ref") or (
            f"builtin:{config['champion']}" if config.get("champion") else None),
        "challenger": config.get("challenger_ref") or (
            f"builtin:{config['challenger']}" if config.get("challenger") else None),
        "beta": config.get("beta_ref") or (
            f"builtin:{config['beta']}" if config.get("beta") else None),
    }

    strategies = {
        role: strategy_fingerprint(ref, {**policy.get(ref, {}),
                                         **policy.get(_bare(ref), {}),
                                         **params.get(ref, {}),
                                         **params.get(_bare(ref), {})})
        for role, ref in roles.items() if ref
    }

    body = {
        "engine_version": ENGINE_VERSION,
        "metric_version": METRIC_VERSION,
        "dataset": dataset_fingerprint(dataset_ref, seed),
        "strategies": strategies,
        "seed": seed,
        "slice": {"dim": config.get("slice_dim"), "value": config.get("slice_value")},
        "windows": {
            "lookback_months": config.get("lookback_months"),
            "perf_window_months": config.get("perf_window_months"),
        },
        "environment": {
            "id": config.get("env_id", "replay"),
            "ri_mode": config.get("ri_mode"),
        },
        "ri_mode": config.get("ri_mode"),
        "mapping_id": config.get("mapping_id"),
    }
    manifest = {
        "manifest_sha": sha(body),
        "body": body,
        "lineage": {"parent_run_id": parent_run_id, "root_run_id": root_run_id},
        "created_by": created_by,
    }
    return manifest


def _bare(ref: Optional[str]) -> str:
    """'builtin:v2.3' -> 'v2.3' so overrides can be keyed either way."""
    if not ref:
        return ""
    return ref.partition(":")[2] or ref
