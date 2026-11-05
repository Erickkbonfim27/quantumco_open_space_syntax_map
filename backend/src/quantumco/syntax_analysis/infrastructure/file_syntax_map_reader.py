"""Read model do mapa sintático: geometria do snapshot + medidas da análise, em GeoJSON."""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

from quantumco.syntax_analysis.application.queries import SyntaxMap

log = logging.getLogger(__name__)

_BASE_COLUMNS = ["link_id", "osm_way_id", "highway", "zone", "is_bridge", "is_tunnel", "length_m"]


class FileSyntaxMapReader:
    def __init__(self, snapshots_dir: Path, analyses_dir: Path) -> None:
        self._snapshots_dir = snapshots_dir
        self._analyses_dir = analyses_dir
        self._lock = threading.Lock()
        self._cached_dir: Path | None = None
        self._cached: SyntaxMap | None = None

    def _latest(self) -> tuple[Path, Path] | None:
        for folder in sorted(self._analyses_dir.glob("analysis-*"), reverse=True):
            snapshot = self._snapshots_dir / f"snapshot-{folder.name.removeprefix('analysis-')}"
            if (folder / "measures.parquet").is_file() and (snapshot / "network.gpkg").is_file():
                return folder, snapshot
        return None

    def current(self) -> SyntaxMap | None:
        found = self._latest()
        if found is None:
            return None
        with self._lock:
            if found[0] != self._cached_dir:
                self._cached = _load(*found)
                self._cached_dir = found[0]
            return self._cached


def _load(analysis_dir: Path, snapshot_dir: Path) -> SyntaxMap:
    started = time.perf_counter()
    manifest = json.loads((analysis_dir / "manifest.json").read_text(encoding="utf-8"))
    links = gpd.read_file(snapshot_dir / "network.gpkg", layer="links")[
        [*_BASE_COLUMNS, "geometry"]
    ]
    measures = pd.read_parquet(analysis_dir / "measures.parquet")
    for column in measures.columns:
        if column.startswith("c_"):
            # classe inteira; NaN (entorno ou sem valor) vira null no GeoJSON
            measures[column] = measures[column].astype("Int8")
        elif column != "link_id":
            measures[column] = measures[column].round(4)
    merged = links.merge(measures, on="link_id", how="left").to_crs(4326)
    merged["length_m"] = merged["length_m"].round(1)
    merged = merged.replace({np.nan: None})
    body = merged.to_json(drop_id=True, na="null").encode("utf-8")
    log.info(
        "mapa sintático %s carregado: %d trechos, %.1f MB em %.1fs",
        analysis_dir.name,
        len(merged),
        len(body) / 1e6,
        time.perf_counter() - started,
    )
    return SyntaxMap(analysis_id=analysis_dir.name, manifest=manifest, links_geojson=body)
