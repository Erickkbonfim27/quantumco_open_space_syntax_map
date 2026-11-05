from __future__ import annotations

from dataclasses import dataclass

from quantumco.syntax_analysis.domain.radius import Radius


@dataclass(frozen=True, slots=True)
class AnalysisConfig:
    """Parâmetros da metodologia (methodology/vN/analysis.yaml e simplification.yaml)."""

    methodology_version: str
    radii: tuple[Radius, ...]
    radius_n_m: int
    simplification_m: float
    classes: int
    preliminary: bool

    def __post_init__(self) -> None:
        if not self.radii:
            raise ValueError("nenhum raio configurado")
        if self.classes < 2:
            raise ValueError("classes precisa ser ≥ 2")
