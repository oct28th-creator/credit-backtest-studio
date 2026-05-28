"""
Strategy contract and data view abstractions.

An uploaded strategy ``.py`` file must expose three top-level objects:

    STRATEGY_META: dict
        {
            "name": str,
            "version": str,
            "role": str,                         # champion | challenger | beta
            "required_inputs": list[str],        # logical feature names the
                                                 # strategy reads from `features`
            "params": dict[str, dict],           # {param_name: {"type": str,
                                                 #   "default": Any, "min"?: ...,
                                                 #   "max"?: ...}}
        }

    def score(features: dict[str, np.ndarray], params: dict) -> np.ndarray
        Return predicted probability of default (pd_hat) per row, in [0, 1].

    def approve(features: dict[str, np.ndarray], pd_hat: np.ndarray,
                params: dict) -> np.ndarray
        Return a boolean approval mask per row.

The platform feeds ``features`` as a plain dict of logical-name -> numpy array,
resolved from the customer's column mapping (see DataView.as_feature_dict).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Union

import numpy as np


@dataclass
class StrategyResult:
    """Output of running one strategy over one dataset."""

    approve_mask: np.ndarray            # bool[N]
    pd_hat: np.ndarray                  # float[N], values in [0, 1]
    strategy_info: dict = field(default_factory=dict)


class DataView:
    """Wrap a dataset (numpy structured array or dict[str, np.ndarray]) together
    with a logical->physical column mapping.

    ``__getitem__("score")`` resolves "score" through the mapping to the actual
    column name and returns that column. With no mapping entry the logical name
    is used as-is. ``protected`` returns ``None`` (instead of raising) when a
    logical attribute is not present, so callers can skip absent groups.
    """

    def __init__(
        self,
        data: Union[np.ndarray, dict[str, np.ndarray]],
        mapping: Optional[dict[str, str]] = None,
        role_columns: Optional[dict[str, str]] = None,
    ) -> None:
        self._data = data
        self._mapping = dict(mapping or {})
        # role_columns maps a semantic role (e.g. "outcome", "score",
        # "gender") to a physical column name. Used by metrics that need a
        # column whose logical name is not part of required_inputs.
        self._role_columns = dict(role_columns or {})
        self._is_struct = isinstance(data, np.ndarray) and data.dtype.names is not None
        self._n = len(data) if self._is_struct else (
            len(next(iter(data.values()))) if isinstance(data, dict) and data else 0
        )

    # ------------------------------------------------------------------ #
    def _physical(self, logical_name: str) -> str:
        if logical_name in self._mapping:
            return self._mapping[logical_name]
        if logical_name in self._role_columns:
            return self._role_columns[logical_name]
        return logical_name

    def _columns(self) -> set[str]:
        if self._is_struct:
            return set(self._data.dtype.names)
        if isinstance(self._data, dict):
            return set(self._data.keys())
        return set()

    def has(self, logical_name: str) -> bool:
        return self._physical(logical_name) in self._columns()

    def __getitem__(self, logical_name: str) -> np.ndarray:
        col = self._physical(logical_name)
        if col not in self._columns():
            raise KeyError(f"column not available: {logical_name} -> {col}")
        return self._data[col]

    def __len__(self) -> int:
        return self._n

    def protected(self, logical_name: str) -> Optional[np.ndarray]:
        if not self.has(logical_name):
            return None
        return self[logical_name]

    def as_feature_dict(self, names: list[str]) -> dict[str, np.ndarray]:
        """Materialise the requested logical features into a plain dict for the
        strategy sandbox. Missing names are skipped silently — the strategy's
        validation step is responsible for checking required_inputs."""
        out: dict[str, np.ndarray] = {}
        for name in names:
            if self.has(name):
                out[name] = np.asarray(self[name])
        return out

    @property
    def role_columns(self) -> dict[str, str]:
        return dict(self._role_columns)

    @property
    def mapping(self) -> dict[str, str]:
        return dict(self._mapping)
