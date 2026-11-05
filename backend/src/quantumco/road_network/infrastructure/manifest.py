from __future__ import annotations

from dataclasses import asdict
from typing import Any

from quantumco.road_network.domain.snapshot import NetworkSnapshot


def snapshot_name(snapshot: NetworkSnapshot) -> str:
    return f"snapshot-{snapshot.osm_base_timestamp:%Y%m%dT%H%M%SZ}"


def build_manifest(snapshot: NetworkSnapshot, methodology_version: str) -> dict[str, Any]:
    return {
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
