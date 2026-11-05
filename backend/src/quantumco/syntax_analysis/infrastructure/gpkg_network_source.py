"""Lê o snapshot mais recente gerado pela Rede Viária.

Integração entre contextos por ARQUIVO publicado (GeoPackage + manifesto), não por import:
Análise Sintática não conhece o código da Rede Viária (contrato do import-linter).
"""

from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd

from quantumco.syntax_analysis.application.ports import AnalysisInput
from quantumco.syntax_analysis.domain.segmentation import Link


def latest_snapshot_dir(snapshots_dir: Path) -> Path | None:
    candidates = sorted(
        p
        for p in snapshots_dir.glob("snapshot-*")
        if (p / "manifest.json").is_file() and (p / "network.gpkg").is_file()
    )
    return candidates[-1] if candidates else None


class GpkgNetworkSource:
    def __init__(self, snapshots_dir: Path) -> None:
        self._snapshots_dir = snapshots_dir

    def latest(self) -> AnalysisInput | None:
        folder = latest_snapshot_dir(self._snapshots_dir)
        if folder is None:
            return None
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        frame = gpd.read_file(folder / "network.gpkg", layer="links")
        links = tuple(
            Link(
                link_id=str(row.link_id),
                coords=tuple((float(x), float(y)) for x, y in row.geometry.coords),
                in_result_zone=row.zone == "result",
            )
            for row in frame.itertuples(index=False)
        )
        return AnalysisInput(
            snapshot_id=str(manifest["snapshot_id"]), snapshot_name=folder.name, links=links
        )
