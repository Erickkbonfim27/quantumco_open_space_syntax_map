"""Adaptador `SnapshotRepository` em disco (GeoPackage + manifesto JSON).

Provisório até o passo 3 (RustFS via porta `ReleaseStore`).
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from pathlib import Path

import geopandas as gpd
from shapely.geometry import LineString

from quantumco.road_network.domain.snapshot import NetworkSnapshot
from quantumco.road_network.domain.topology import RoadLink

log = logging.getLogger(__name__)


class FileSnapshotRepository:
    def __init__(self, root: Path) -> None:
        self._root = root

    def save(self, snapshot: NetworkSnapshot, methodology_version: str) -> str:
        folder = self._root / f"snapshot-{snapshot.osm_base_timestamp:%Y%m%dT%H%M%SZ}"
        folder.mkdir(parents=True, exist_ok=True)
        crs = f"EPSG:{snapshot.study_area.crs_epsg}"

        gpkg = folder / "network.gpkg"
        log.info("gravando %d trechos em %s", len(snapshot.links), gpkg)
        _frame(snapshot.links, crs).to_file(gpkg, layer="links", driver="GPKG")
        gpd.GeoDataFrame(
            {"ibge_code": [snapshot.study_area.ibge_code]},
            geometry=[snapshot.municipality],
            crs=crs,
        ).to_file(gpkg, layer="municipality", driver="GPKG")
        if snapshot.excluded_links:
            _frame(snapshot.excluded_links, crs).to_file(
                gpkg, layer="excluded_disconnected", driver="GPKG"
            )

        manifest = {
            "snapshot_id": str(snapshot.snapshot_id),
            "methodology_version": methodology_version,
            "filter_version": snapshot.filter_version,
            "osm_base_timestamp": snapshot.osm_base_timestamp.isoformat(),
            "source": snapshot.source,
            "created_at": snapshot.created_at.isoformat(),
            "study_area": asdict(snapshot.study_area),
            "cleaning_report": asdict(snapshot.report),
            "license": "ODbL-1.0, © OpenStreetMap contributors",
        }
        log.info("gravando manifesto em %s", folder / "manifest.json")
        (folder / "manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return str(folder)


def _frame(links: tuple[RoadLink, ...], crs: str) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {
            "link_id": [link.link_id for link in links],
            "osm_way_id": [link.osm_way_id for link in links],
            "from_node": [link.from_node for link in links],
            "to_node": [link.to_node for link in links],
            "highway": [link.highway for link in links],
            "zone": [link.zone.value for link in links],
            "is_bridge": [link.is_bridge for link in links],
            "is_tunnel": [link.is_tunnel for link in links],
            "length_m": [link.length_m for link in links],
        },
        geometry=[LineString(link.coords) for link in links],
        crs=crs,
    )
