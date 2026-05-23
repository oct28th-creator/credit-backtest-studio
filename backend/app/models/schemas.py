from typing import Optional
from pydantic import BaseModel


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
    language: str = "zh"  # "zh" or "en"


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
    language: str = "zh"


class AIChatRequest(BaseModel):
    run_id: str
    message: str
    history: list[dict]
    layer: Optional[str] = None
    language: str = "zh"


class NLParseRequest(BaseModel):
    text: str
    language: str = "zh"
