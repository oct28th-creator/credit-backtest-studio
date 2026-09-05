from typing import Literal, Optional
from pydantic import BaseModel, Field

Language = Literal["zh", "en"]


class ExperimentConfig(BaseModel):
    challenger: str = "v2.3"
    champion: str = "v2.2"
    beta: Optional[str] = "v2.4-Beta"
    sample_id: str = "consumer_2024q1q2"
    lookback_months: int = 6
    perf_window_months: int = 12
    ri_mode: str = "parceling"
    slice_dim: Optional[str] = None
    slice_value: Optional[str] = None
    language: Language = "zh"

    # Custom-backtest refs (optional, backward compatible). When any of these is
    # set the run uses the custom orchestration path. Refs look like
    # "builtin:v2.2" or "custom:<id>"; dataset_ref like "builtin:<sample_id>"
    # or "custom:<dataset_id>".
    champion_ref: Optional[str] = None
    challenger_ref: Optional[str] = None
    beta_ref: Optional[str] = None
    dataset_ref: Optional[str] = None
    mapping_id: Optional[str] = None

    # ── Agentic experiment knobs (all optional, backward compatible) ──────
    # seed makes the synthetic book resamplable: an agent can repeat a
    # comparison across seeds instead of over-reading one draw.
    seed: int = 42
    # Policy knobs for built-in strategies, keyed by ref ("builtin:v2.3") or
    # bare id ("v2.3"): {"v2.3": {"target_approval_rate": 0.5, "dti_limit": 0.7}}
    policy_overrides: dict[str, dict] = Field(default_factory=dict)
    # Params for uploaded strategies, same keying, merged over STRATEGY_META
    # defaults before the sandbox call.
    param_overrides: dict[str, dict] = Field(default_factory=dict)


class RunSubmit(BaseModel):
    """Asynchronous run request (agents fire many; nobody waits on a socket)."""

    config: ExperimentConfig
    created_by: str = Field(default="user", max_length=120)
    hypothesis: Optional[str] = Field(default=None, max_length=2000)
    tags: list[str] = Field(default_factory=list, max_length=20)


class RunAnnotation(BaseModel):
    """What the run was for and what it showed — the registry's memory."""

    hypothesis: Optional[str] = Field(default=None, max_length=2000)
    conclusion: Optional[str] = Field(default=None, max_length=4000)
    tags: Optional[list[str]] = Field(default=None, max_length=20)


class StrategyUpload(BaseModel):
    name: Optional[str] = Field(default=None, max_length=200)
    code: str = Field(..., max_length=200_000)  # ~200 KB of source is ample


class ColumnMapping(BaseModel):
    dataset_id: str
    strategy_id: str
    mapping: dict[str, str]        # logical feature name -> dataset column name
    role_columns: dict[str, str]   # semantic role (outcome/score/...) -> column


class RunResult(BaseModel):
    run_id: str
    champion: str
    challenger: str
    beta: Optional[str]
    sample_size: int
    duration_s: float
    snapshot_sha: str
    config: ExperimentConfig
    layers: dict  # L1-L5 computed results


class SliceRequest(BaseModel):
    slice_dim: Optional[str]
    slice_value: Optional[str]


class AILayerRequest(BaseModel):
    run_id: str
    layer: str  # l1..l5
    language: Language = "zh"


class AIChatRequest(BaseModel):
    run_id: str
    message: str = Field(..., max_length=4000)
    history: list[dict] = Field(default_factory=list, max_length=50)
    layer: Optional[str] = None
    language: Language = "zh"


class NLParseRequest(BaseModel):
    text: str = Field(..., max_length=4000)
    language: Language = "zh"
