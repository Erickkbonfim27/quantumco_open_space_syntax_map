from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from quantumco.road_network.domain.highway_filter import HighwayFilter


class YamlMethodology:
    """Lê `methodology/vN/` do repositório. A pasta versionada é a fonte da verdade."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def _load(self, name: str) -> dict[str, Any]:
        with (self._root / name).open(encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
        if not isinstance(data, dict):
            raise ValueError(f"{name}: esperado um mapeamento YAML")
        return data

    def version(self) -> str:
        return (self._root / "VERSION").read_text(encoding="utf-8").strip()

    def buffer_m(self) -> float:
        """Faixa externa da área de estudo (o município sai do cadastro de cidades)."""
        return float(self._load("study_area.yaml")["buffer_m"])

    def highway_filter(self) -> HighwayFilter:
        data = self._load("highway_filter.yaml")

        def values(key: str) -> frozenset[str]:
            return frozenset(str(v) for v in data.get(key, []))

        return HighwayFilter(
            version=str(data["version"]),
            included=values("included"),
            link_variants_of=values("link_variants_of"),
            buffer_only=values("buffer_only"),
            pedestrian_variant=values("pedestrian_variant"),
            excluded_service=values("excluded_service"),
            excluded_access=values("excluded_access"),
        )
