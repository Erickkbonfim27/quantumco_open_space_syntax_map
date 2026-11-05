from __future__ import annotations

from pathlib import Path

import yaml

from quantumco.syntax_analysis.application.config import AnalysisConfig
from quantumco.syntax_analysis.domain.radius import Radius


def load_analysis_config(methodology_dir: Path) -> AnalysisConfig:
    analysis = yaml.safe_load((methodology_dir / "analysis.yaml").read_text(encoding="utf-8"))
    simplification = yaml.safe_load(
        (methodology_dir / "simplification.yaml").read_text(encoding="utf-8")
    )
    radii = (*tuple(Radius(int(m)) for m in analysis["radii_m"]), Radius(None))
    return AnalysisConfig(
        methodology_version=(methodology_dir / "VERSION").read_text(encoding="utf-8").strip(),
        radii=radii,
        radius_n_m=int(analysis["radius_n_m"]),
        simplification_m=float(simplification["douglas_peucker_tolerance_m"]),
        classes=int(analysis["classes"]),
        preliminary=bool(analysis.get("preliminary", True)),
    )
