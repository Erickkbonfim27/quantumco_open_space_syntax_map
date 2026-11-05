"""Adaptador `PublishedNetworkReader` que lê o snapshot mais recente do disco.

A conversão para GeoJSON é feita uma vez por snapshot e fica em memória. Quando um snapshot
novo aparece na pasta (rodada semanal ou cold start), a próxima requisição recarrega.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path

import geopandas as gpd

from quantumco.road_network.application.queries import PublishedNetwork

log = logging.getLogger(__name__)

_LINK_COLUMNS = ["link_id", "osm_way_id", "highway", "zone", "is_bridge", "is_tunnel", "length_m"]


def latest_snapshot_dir(snapshots_dir: Path) -> Path | None:
    candidates = sorted(
        p
        for p in snapshots_dir.glob("snapshot-*")
        if (p / "manifest.json").is_file() and (p / "network.gpkg").is_file()
    )
    return candidates[-1] if candidates else None


class FileNetworkReader:
    def __init__(self, snapshots_dir: Path) -> None:
        self._snapshots_dir = snapshots_dir
        self._lock = threading.Lock()
        self._cached_dir: Path | None = None
        self._cached: PublishedNetwork | None = None

    def current(self) -> PublishedNetwork | None:
        latest = latest_snapshot_dir(self._snapshots_dir)
        if latest is None:
            return None
        with self._lock:
            if latest != self._cached_dir:
                self._cached = _load(latest)
                self._cached_dir = latest
            return self._cached


def _load(folder: Path) -> PublishedNetwork:
    started = time.perf_counter()
    gpkg = folder / "network.gpkg"
    layers = set(gpd.list_layers(gpkg)["name"].tolist())
    if "municipality" not in layers:
        raise FileNotFoundError(
            f"{folder.name} não tem a camada 'municipality' (snapshot antigo); "
            "rode `quantumco snapshot build` de novo"
        )
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))

    links = gpd.read_file(gpkg, layer="links")[[*_LINK_COLUMNS, "geometry"]].to_crs(4326)
    links["length_m"] = links["length_m"].round(1)
    municipality = gpd.read_file(gpkg, layer="municipality").to_crs(4326)

    network = PublishedNetwork(
        snapshot_id=str(manifest["snapshot_id"]),
        manifest=manifest,
        links_geojson=links.to_json(drop_id=True).encode("utf-8"),
        municipality_geojson=municipality.to_json(drop_id=True).encode("utf-8"),
    )
    log.info(
        "snapshot %s carregado: %d trechos, %.1f MB de GeoJSON em %.1fs",
        folder.name,
        len(links),
        len(network.links_geojson) / 1e6,
        time.perf_counter() - started,
    )
    return network
