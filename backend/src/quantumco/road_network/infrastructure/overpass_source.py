"""Adaptadores `OsmWaySource` e `BoundaryLocator` via Overpass API.

O carimbo `timestamp_osm_base` da resposta vai para o snapshot. Para reproduzir um extrato
antigo, passe `as_of` (consulta "attic" do Overpass com `[date:...]`).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import httpx
from pyproj import Transformer
from shapely.geometry import LineString, MultiPolygon, Polygon
from shapely.ops import polygonize, transform, unary_union

from quantumco.road_network.application.ports import BoundaryRef
from quantumco.road_network.domain.osm import OsmExtract, OsmWay
from quantumco.road_network.domain.study_area import StudyArea

DEFAULT_URL = "https://overpass-api.de/api/interpreter"
USER_AGENT = "quantumco/1.0 (mapa sintatico aberto; +https://quantumco.com.br)"
_RETRYABLE = frozenset({429, 502, 503, 504})

log = logging.getLogger(__name__)


class OverpassError(RuntimeError):
    pass


class OverpassWaySource:
    def __init__(
        self,
        *,
        url: str = DEFAULT_URL,
        timeout_s: float = 300.0,
        as_of: datetime | None = None,
        client: httpx.Client | None = None,
        max_attempts: int = 6,
        initial_backoff_s: float = 15.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._url = url
        self._timeout_s = timeout_s
        self._as_of = as_of
        self._max_attempts = max_attempts
        self._initial_backoff_s = initial_backoff_s
        self._sleep = sleep
        self._client = client or httpx.Client(timeout=timeout_s, headers={"User-Agent": USER_AGENT})

    def _settings(self) -> str:
        date = f'[date:"{self._as_of.strftime("%Y-%m-%dT%H:%M:%SZ")}"]' if self._as_of else ""
        return f"[out:json][timeout:{int(self._timeout_s)}]{date};"

    def _query(self, body: str, label: str = "consulta") -> dict[str, Any]:
        delay = self._initial_backoff_s
        for attempt in range(1, self._max_attempts + 1):
            log.info(
                "Overpass [%s]: enviando (tentativa %d/%d)", label, attempt, self._max_attempts
            )
            started = time.perf_counter()
            response = self._client.post(self._url, data={"data": self._settings() + body})
            elapsed = time.perf_counter() - started
            if response.status_code not in _RETRYABLE or attempt == self._max_attempts:
                break
            log.warning(
                "Overpass [%s]: servidor ocupado (HTTP %d em %.1fs); nova tentativa em %.0fs",
                label,
                response.status_code,
                elapsed,
                delay,
            )
            self._sleep(delay)
            delay *= 2
        if response.status_code != 200:
            log.error("Overpass [%s]: falhou com HTTP %d", label, response.status_code)
            raise OverpassError(f"Overpass {response.status_code}: {response.text[:300]}")
        log.info(
            "Overpass [%s]: HTTP 200 em %.1fs, %.1f MB",
            label,
            elapsed,
            len(response.content) / 1e6,
        )
        payload: dict[str, Any] = response.json()
        if "remark" in payload and "runtime error" in str(payload["remark"]):
            raise OverpassError(str(payload["remark"]))
        return payload

    def find(self, ibge_code: str) -> BoundaryRef | None:
        """Relação do limite municipal pelo código IBGE (nunca pelo nome, Q14)."""
        payload = self._query(
            'rel["boundary"="administrative"]["admin_level"="8"]'
            f'["IBGE:GEOCODIGO"="{ibge_code}"];out ids center;',
            label=f"limite IBGE {ibge_code}",
        )
        relations = [el for el in payload["elements"] if el["type"] == "relation"]
        if len(relations) != 1:
            if relations:
                log.warning(
                    "IBGE %s: %d relações no OSM; nenhuma escolhida", ibge_code, len(relations)
                )
            return None
        center = relations[0].get("center") or {}
        if "lon" not in center:
            return None
        return BoundaryRef(
            osm_relation_id=int(relations[0]["id"]),
            center=(float(center["lon"]), float(center["lat"])),
        )

    def fetch(self, area: StudyArea) -> OsmExtract:
        to_crs = Transformer.from_crs(4326, area.crs_epsg, always_xy=True)
        to_wgs = Transformer.from_crs(area.crs_epsg, 4326, always_xy=True)

        boundary_payload = self._query(
            f"rel({area.osm_relation_id});out geom;", label="limite municipal"
        )
        municipality_wgs = _relation_polygon(boundary_payload, area)
        municipality = transform(to_crs.transform, municipality_wgs)
        log.info(
            "limite municipal: relação %d (IBGE %s), %.0f km²",
            area.osm_relation_id,
            area.ibge_code,
            municipality.area / 1e6,
        )

        study_polygon = municipality.buffer(area.buffer_m).simplify(100.0)
        study_wgs = transform(to_wgs.transform, study_polygon)
        poly = " ".join(f"{lat:.6f} {lon:.6f}" for lon, lat in _exterior(study_wgs))
        log.info(
            "área de estudo com buffer de %.0f km: %.0f km²",
            area.buffer_m / 1000,
            study_polygon.area / 1e6,
        )

        ways_payload = self._query(f'way["highway"](poly:"{poly}");out body geom;', label="vias")
        elements = [el for el in ways_payload["elements"] if el["type"] == "way"]
        log.info("projetando %d vias para EPSG:%d", len(elements), area.crs_epsg)
        ways = tuple(_to_way(el, to_crs) for el in elements)

        stamp = ways_payload.get("osm3s", {}).get("timestamp_osm_base")
        if not stamp:
            raise OverpassError("resposta sem timestamp_osm_base")
        osm_base = datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone(UTC)

        if not isinstance(municipality, Polygon):
            raise OverpassError("limite municipal não é um polígono simples")
        return OsmExtract(
            ways=ways,
            municipality=municipality,
            osm_base_timestamp=osm_base,
            source=f"overpass:{self._url}",
        )


def _relation_polygon(payload: dict[str, Any], area: StudyArea) -> Polygon:
    relations = [el for el in payload["elements"] if el["type"] == "relation"]
    if len(relations) != 1:
        raise OverpassError(f"relação {area.osm_relation_id} não encontrada")
    relation = relations[0]
    code = relation.get("tags", {}).get("IBGE:GEOCODIGO")
    if code != area.ibge_code:
        raise OverpassError(
            f"relação {area.osm_relation_id} tem IBGE:GEOCODIGO={code!r}, "
            f"esperado {area.ibge_code!r}"
        )

    def rings(role: str) -> list[LineString]:
        return [
            LineString([(p["lon"], p["lat"]) for p in member["geometry"]])
            for member in relation["members"]
            if member["type"] == "way" and member.get("role") == role and "geometry" in member
        ]

    outer = unary_union(list(polygonize(rings("outer"))))
    inner = unary_union(list(polygonize(rings("inner"))))
    shape = outer.difference(inner) if not inner.is_empty else outer
    if isinstance(shape, MultiPolygon):
        shape = max(shape.geoms, key=lambda g: g.area)
    if not isinstance(shape, Polygon) or shape.is_empty:
        raise OverpassError("não foi possível montar o polígono do município")
    return shape


def _exterior(shape: Any) -> list[tuple[float, float]]:
    polygon = max(shape.geoms, key=lambda g: g.area) if isinstance(shape, MultiPolygon) else shape
    return [(float(x), float(y)) for x, y in polygon.exterior.coords[:-1]]


def _to_way(element: dict[str, Any], to_crs: Transformer) -> OsmWay:
    coords = tuple(
        (float(x), float(y))
        for x, y in (to_crs.transform(p["lon"], p["lat"]) for p in element["geometry"])
    )
    return OsmWay(
        osm_id=int(element["id"]),
        node_ids=tuple(int(n) for n in element["nodes"]),
        coords=coords,
        tags={str(k): str(v) for k, v in element.get("tags", {}).items()},
    )
