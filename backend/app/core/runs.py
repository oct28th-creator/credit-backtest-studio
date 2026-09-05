"""Run execution service.

Everything about *running* an experiment lives here: the hot run cache, the
metric reshaping, config validation and the single ``execute_run`` path that
gives every run a manifest, a lineage and a persisted record.

It is deliberately free of FastAPI: the HTTP router (api/experiments.py) and
the agent tool layer (agent/tools.py) are both callers, and neither should be
able to produce a run the other could not.
"""
from __future__ import annotations

import uuid
import asyncio
import logging
from typing import Optional

from app.models.schemas import ExperimentConfig
from app.services.metrics import run_backtest, run_backtest_custom
from app.services.stability import compute_csi
from app.data.fixtures import STRATEGIES
from app.db import repository
from app.core.manifest import build_manifest, ENGINE_VERSION, METRIC_VERSION

logger = logging.getLogger("backtest.runs")


class RunNotFound(Exception):
    """No run with this id, in cache or in SQLite."""

    def __init__(self, run_id: str) -> None:
        super().__init__(f"Run not found: {run_id}")
        self.run_id = run_id


class ConfigInvalid(ValueError):
    """The experiment configuration references something that does not exist."""


# In-memory store, used as a hot read cache in front of the SQLite `runs`
# table. It is rehydrated from SQLite on startup (see ``rehydrate_run_store``)
# so completed runs survive a service restart.
_RUN_STORE: dict[str, dict] = {}


def rehydrate_run_store() -> int:
    """Reload persisted runs from SQLite into the in-memory store on startup.

    Returns the number of runs loaded. Best-effort: a failure here must not
    stop the API from booting, so it is caught and logged.
    """
    try:
        runs = repository.load_all_runs()
    except Exception:  # noqa: BLE001
        logger.exception("failed to rehydrate run store from SQLite")
        return 0
    for run_id, result in runs:
        _RUN_STORE[run_id] = result
    if runs:
        logger.info("rehydrated %d run(s) from SQLite", len(runs))
    return len(runs)

def get_run(run_id: str) -> dict:
    """Fetch a run from the hot cache, falling back to SQLite on a miss.

    The store is rehydrated on startup, but an entry can still be missing
    (e.g. rehydration failed or the process was restarted mid-request), so
    a cache miss re-checks the persisted row before returning 404.
    """
    run = _RUN_STORE.get(run_id)
    if run is not None:
        return run
    try:
        stored = repository.get_run(run_id)
    except Exception:  # noqa: BLE001 — treat a broken DB as a plain miss
        logger.exception("SQLite lookup failed for run %s", run_id)
        stored = None
    result = stored.get("result") if stored else None
    if isinstance(result, dict) and result:
        _RUN_STORE[run_id] = result
        return result
    raise RunNotFound(run_id)


_MONTH_LABELS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                 "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _psi_tone(psi: float) -> str:
    if psi < 0.10:
        return "green"
    if psi < 0.25:
        return "amber"
    return "red"


def _reshape_layers(raw: dict, strategy_ids: list[str], challenger_id: str, beta_id: Optional[str]) -> dict:
    """
    Reshape backend's per-strategy layer structure into the frontend's
    per-layer structure with all strategy comparisons combined within each layer.
    """
    out: dict = {}

    # ── L1: Model quality ────────────────────────────────────────────────────
    l1_kpis = []
    l1_roc: dict = {}
    l1_calib: dict = {}
    l1_psi_monthly = None
    l1_csi = None

    for sid in strategy_ids:
        s = raw.get(sid, {}).get("l1", {})
        l1_kpis.append({
            "version": sid,
            "ks": round(s.get("ks", 0), 4),
            "auc": round(s.get("auc", 0), 4),
            "lift20": round(s.get("lift_at_20", 0), 3),
            "brier": round(s.get("brier_score", 0), 4),
        })
        l1_roc[sid] = s.get("roc_curve", [])
        # Chart expects {pd_pred, actual}; backend emits {predicted, actual}.
        l1_calib[sid] = [
            {"pd_pred": p.get("predicted", 0), "actual": p.get("actual", 0)}
            for p in s.get("calibration", [])
        ]

        # Use challenger's PSI trend as the primary monthly trend
        if sid == challenger_id and "psi_trend" in s:
            l1_psi_monthly = [
                {
                    "month": _MONTH_LABELS[i] if i < len(_MONTH_LABELS) else pt["month"],
                    "psi": pt["psi"],
                    "tone": _psi_tone(pt["psi"]),
                }
                for i, pt in enumerate(s["psi_trend"])
            ]

    # Characteristic Stability Index for the challenger's key features
    l1_csi = compute_csi(challenger_id)

    if l1_psi_monthly is None and strategy_ids:
        first = raw.get(strategy_ids[0], {}).get("l1", {})
        l1_psi_monthly = [
            {"month": _MONTH_LABELS[i] if i < len(_MONTH_LABELS) else pt["month"],
             "psi": pt["psi"], "tone": _psi_tone(pt["psi"])}
            for i, pt in enumerate(first.get("psi_trend", []))
        ]

    out["l1"] = {
        "kpis": l1_kpis,
        "psi_monthly": l1_psi_monthly or [],
        "roc": l1_roc,
        "calibration": l1_calib,
        "csi": l1_csi or [],
    }

    # ── L2: Business value ───────────────────────────────────────────────────
    l2_kpis = []
    l2_frontier = None
    l2_rejection_reasons: dict = {}
    l2_raroc_bands: dict = {}

    for sid in strategy_ids:
        s = raw.get(sid, {}).get("l2", {})
        apr = s.get("approval_rate", 0)
        raroc = s.get("raroc", 0)
        bad_rate = s.get("bad_rate", 0)
        avg_profit = s.get("avg_profit_per_approved", 0)

        l2_kpis.append({
            "version": sid,
            "approval_rate": round(apr, 4),          # fraction (UI ×100)
            "avg_profit": round(avg_profit, 0),
            "raroc": round(raroc, 4),                # fraction
            "el": round(bad_rate, 4),                # bad rate fraction (EL proxy)
        })

        # Pareto frontier (use challenger's). Chart reads {approval_rate, avg_profit}
        # and scales the x-axis by 100, so approval_rate stays a fraction here.
        if sid == challenger_id and "pareto_frontier" in s:
            l2_frontier = [
                {"approval_rate": round(p["approval_rate"], 4), "avg_profit": round(p["avg_profit"], 0)}
                for p in s["pareto_frontier"]
            ]

        # Simulated rejection reasons per strategy
        l2_rejection_reasons[sid] = s.get("rejection_reasons", [])
        l2_raroc_bands[sid] = s.get("raroc_bands", [])

    out["l2"] = {
        "kpis": l2_kpis,
        "frontier": l2_frontier or [],
        "rejection_reasons": l2_rejection_reasons,
        "raroc_bands": l2_raroc_bands,
    }

    # ── L3: Risk ──────────────────────────────────────────────────────────────
    l3_kpis = []
    l3_vintage_points: list = []
    l3_fpd_trend: list = []
    l3_roll_rates: dict = {}

    mob_months = list(range(1, 13))
    for sid in strategy_ids:
        s = raw.get(sid, {}).get("l3", {})
        rr = s.get("roll_rates", {})

        l3_kpis.append({
            "version": sid,
            "m12_bad": round(s.get("mob12_bad_rate", 0), 4),
            "m1_m2_roll": round(rr.get("m1_to_m2", 0), 4),
            "fpd": round(s.get("fpd_rate", 0), 4),
        })
        l3_roll_rates[sid] = {
            "m0_m1": round(rr.get("m0_to_m1", 0), 4),
            "m1_m2": round(rr.get("m1_to_m2", 0), 4),
            "m2_m3plus": round(rr.get("m2_to_m3plus", 0), 4),
        }

        # Build vintage (indexed by MOB)
        vc = {pt["month"]: pt["cum_bad_rate"] for pt in s.get("vintage_curve", [])}
        for m in mob_months:
            # Find or create entry
            existing = next((x for x in l3_vintage_points if x["mob"] == m), None)
            if existing is None:
                entry = {"mob": m}
                l3_vintage_points.append(entry)
                existing = entry
            existing[sid] = round(vc.get(m, 0), 5)

        # FPD trend
        fpd_raw = s.get("fpd_monthly_trend", [])
        for i, pt in enumerate(fpd_raw):
            month_label = _MONTH_LABELS[i] if i < len(_MONTH_LABELS) else pt["month"]
            existing = next((x for x in l3_fpd_trend if x["month"] == month_label), None)
            if existing is None:
                entry = {"month": month_label}
                l3_fpd_trend.append(entry)
                existing = entry
            existing[sid] = round(pt["fpd_rate"], 5)

    l3_vintage_points.sort(key=lambda x: x["mob"])

    out["l3"] = {
        "kpis": l3_kpis,
        "vintage": l3_vintage_points,
        "fpd_trend": l3_fpd_trend,
        "roll_rates": l3_roll_rates,
    }

    # ── L4: Swap-set matrices ─────────────────────────────────────────────────
    def _reshape_swap(swap: dict) -> dict:
        n_total = (
            swap.get("double_approve", {}).get("n", 0)
            + swap.get("swap_in", {}).get("n", 0)
            + swap.get("swap_out", {}).get("n", 0)
            + swap.get("double_reject", {}).get("n", 0)
        )
        cons = swap.get("consistency_pct", 0)
        return {
            "double_approve": {
                "count": swap.get("double_approve", {}).get("n", 0),
                "bad_rate": round(swap.get("double_approve", {}).get("bad_rate", 0), 4),
            },
            "swap_in": {
                "count": swap.get("swap_in", {}).get("n", 0),
                "bad_rate": round(swap.get("swap_in", {}).get("bad_rate", 0), 4),
            },
            "swap_out": {
                "count": swap.get("swap_out", {}).get("n", 0),
                "bad_rate": round(swap.get("swap_out", {}).get("bad_rate", 0), 4),
            },
            "double_reject": {
                "count": swap.get("double_reject", {}).get("n", 0),
                "bad_rate": None,
            },
            "consistency": round(cons, 4),
            "consistency_count": int(n_total * cons),
            "consistency_total": n_total,
            "p_value": swap.get("p_value", 1.0),
            "base_bad_rate": round(swap.get("base_bad_rate", 0), 4),
            "swap_out_lift": swap.get("swap_out_lift", 0.0),
            "consistency_by_band": [
                {"band": b["score_band"], "consistency": round(b["consistency_pct"], 4)}
                for b in swap.get("score_band_consistency", [])
            ],
        }

    l4_matrices: dict = {}
    if "_swap_chall_vs_champ" in raw:
        l4_matrices[challenger_id] = _reshape_swap(raw["_swap_chall_vs_champ"])
    if beta_id and "_swap_beta_vs_champ" in raw:
        l4_matrices[beta_id] = _reshape_swap(raw["_swap_beta_vs_champ"])

    out["l4"] = {"matrices": l4_matrices}

    # ── L5: Fairness ──────────────────────────────────────────────────────────
    l5_di_by_group: dict = {}
    l5_shap: dict = {}
    l5_kpis: dict = {}

    for sid in strategy_ids:
        s = raw.get(sid, {}).get("l5", {})
        groups = {g["group"]: g["di_ratio"] for g in s.get("di_ratios", [])}

        female_male = groups.get("female_vs_male", 0.90)
        young_core = groups.get("young_vs_core", 0.90)
        partner_online = groups.get("partner_vs_online", 0.90)

        l5_di_by_group[sid] = {
            "female_male": round(female_male, 3),
            "outsider_local": round(partner_online, 3),
            "young_core": round(young_core, 3),
        }
        l5_shap[sid] = [
            {"feature": f["feature"],
             "shap": round(f["importance"] * (1 if f.get("direction") == "positive" else -1), 4)}
            for f in s.get("feature_importance", [])
        ]

        if sid == challenger_id:
            champ_data = raw.get(strategy_ids[0], {}).get("l5", {})
            champ_groups = {g["group"]: g["di_ratio"] for g in champ_data.get("di_ratios", [])}
            champ_fm = champ_groups.get("female_vs_male", female_male)
            tpr_fm = next(
                (g["tpr_gap"] for g in s.get("tpr_gaps", []) if g["group"] == "female_vs_male"),
                0.0,
            )
            # Reason coverage = share of declines explained by a concrete rule
            # (i.e. not falling into the "其他" bucket). Fraction; UI ×100.
            chall_rej = l2_rejection_reasons.get(challenger_id, [])
            covered = sum(r["pct"] for r in chall_rej if r["reason"] != "其他")
            l5_kpis = {
                "di_female_male": round(female_male, 3),
                "di_delta_vs_champ": round(female_male - champ_fm, 3),
                "tpr_gap": round(tpr_fm, 4),
                "reason_coverage": round(covered, 3) if chall_rej else 1.0,
            }

    out["l5"] = {
        "kpis": l5_kpis,
        "di_by_group": l5_di_by_group,
        "shap": l5_shap,
    }

    return out


def _is_custom_config(config: ExperimentConfig) -> bool:
    return any([
        config.champion_ref, config.challenger_ref,
        config.beta_ref, config.dataset_ref,
    ])


def _run_and_reshape(run_id: str, config: ExperimentConfig) -> dict:
    """Run a full backtest (CPU-bound) and assemble the frontend result.

    Pure/synchronous — intended to be dispatched via ``asyncio.to_thread`` so
    the heavy NumPy work does not block the event loop.
    """
    if _is_custom_config(config):
        dataset_ref = config.dataset_ref or f"builtin:{config.sample_id}"
        dataset_is_builtin = dataset_ref.startswith("builtin:")
        champion_ref = config.champion_ref or f"builtin:{config.champion}"
        challenger_ref = config.challenger_ref or f"builtin:{config.challenger}"
        # Only fall back to the legacy builtin beta when the dataset is also
        # builtin; a custom dataset cannot feed a builtin strategy.
        beta_ref = config.beta_ref
        if beta_ref is None and dataset_is_builtin and config.beta:
            beta_ref = f"builtin:{config.beta}"

        raw = run_backtest_custom(
            champion_ref=champion_ref,
            challenger_ref=challenger_ref,
            beta_ref=beta_ref,
            dataset_ref=dataset_ref,
            mapping_id=config.mapping_id,
            seed=config.seed,
            policy_overrides=config.policy_overrides,
            param_overrides=config.param_overrides,
        )
        strategy_ids = raw.get("strategy_ids", [champion_ref, challenger_ref])
        frontend_layers = _reshape_layers(raw["layers"], strategy_ids, challenger_ref, beta_ref)
        return {
            "run_id": run_id,
            "champion": champion_ref,
            "challenger": challenger_ref,
            "beta": beta_ref,
            "sample_size": raw["sample_size"],
            "duration_s": raw["duration_s"],
            "snapshot_sha": raw["snapshot_sha"],
            "config": config.model_dump(),
            "layers": frontend_layers,
        }

    raw = run_backtest(
        champion_id=config.champion,
        challenger_id=config.challenger,
        beta_id=config.beta,
        sample_id=config.sample_id,
        slice_dim=config.slice_dim,
        slice_value=config.slice_value,
        seed=config.seed,
        policy_overrides=config.policy_overrides,
    )

    strategy_ids = raw.get("strategy_ids", [config.champion, config.challenger])
    if config.beta and config.beta not in strategy_ids:
        strategy_ids.append(config.beta)

    frontend_layers = _reshape_layers(raw["layers"], strategy_ids, config.challenger, config.beta)

    return {
        "run_id": run_id,
        "champion": config.champion,
        "challenger": config.challenger,
        "beta": config.beta,
        "sample_size": raw["sample_size"],
        "duration_s": raw["duration_s"],
        "snapshot_sha": raw["snapshot_sha"],
        "config": config.model_dump(),
        "layers": frontend_layers,
    }


def _validate_ref(ref: Optional[str], label: str) -> None:
    if not ref:
        return
    if ref.startswith("builtin:"):
        sid = ref.split(":", 1)[1]
        if sid not in STRATEGIES:
            raise ConfigInvalid(f"Unknown builtin {label}: {sid}")
    elif ref.startswith("custom:"):
        cid = ref.split(":", 1)[1]
        if repository.get_custom_strategy(cid) is None:
            raise ConfigInvalid(f"Unknown custom {label}: {cid}")
    else:
        raise ConfigInvalid(f"Invalid {label} ref: {ref}")


def validate_config(config: ExperimentConfig) -> None:
    """Reject unknown strategies/datasets before any compute is spent."""
    if _is_custom_config(config):
        _validate_ref(config.champion_ref, "champion")
        _validate_ref(config.challenger_ref, "challenger")
        _validate_ref(config.beta_ref, "beta")
        if config.dataset_ref and config.dataset_ref.startswith("custom:"):
            cid = config.dataset_ref.split(":", 1)[1]
            if repository.get_custom_dataset(cid) is None:
                raise ConfigInvalid(f"Unknown custom dataset: {cid}")
    else:
        for sid in [config.champion, config.challenger]:
            if sid not in STRATEGIES:
                raise ConfigInvalid(f"Unknown strategy: {sid}")
        if config.beta and config.beta not in STRATEGIES:
            raise ConfigInvalid(f"Unknown beta strategy: {config.beta}")


def new_run_id() -> str:
    return str(uuid.uuid4())[:12]


async def execute_run(
    run_id: str,
    config: ExperimentConfig,
    *,
    parent_run_id: Optional[str] = None,
    root_run_id: Optional[str] = None,
    created_by: str = "user",
    hypothesis: Optional[str] = None,
    tags: Optional[list] = None,
) -> dict:
    """Compute one run and persist it as an immutable record.

    Every run — first, resliced, or agent-generated — goes through here, so
    every run gets a manifest, a lineage and a status. Nothing overwrites an
    earlier run: a variation is always a new run_id.
    """
    manifest = build_manifest(
        config.model_dump(),
        parent_run_id=parent_run_id,
        root_run_id=root_run_id or run_id,
        created_by=created_by,
    )
    result = await asyncio.to_thread(_run_and_reshape, run_id, config)
    result["manifest_sha"] = manifest["manifest_sha"]
    result["parent_run_id"] = parent_run_id
    result["root_run_id"] = root_run_id or run_id
    result["created_by"] = created_by
    result["engine_version"] = ENGINE_VERSION
    result["metric_version"] = METRIC_VERSION

    _RUN_STORE[run_id] = result
    try:
        repository.create_run(
            run_id, config.model_dump(), result, result.get("snapshot_sha", ""),
            manifest=manifest, parent_run_id=parent_run_id,
            root_run_id=root_run_id or run_id, status="succeeded",
            created_by=created_by, hypothesis=hypothesis, tags=tags,
        )
    except Exception:  # noqa: BLE001 — persistence is best-effort; the run is
        # still served from the in-memory store, but log so the failure is
        # visible instead of silently dropping the record.
        logger.exception("failed to persist run %s to SQLite", run_id)
    return result


