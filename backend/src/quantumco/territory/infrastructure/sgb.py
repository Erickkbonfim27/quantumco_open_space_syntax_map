"""SGB (Serviço Geológico do Brasil): setores de risco geológico e cartas de suscetibilidade.

WFS público em geoservicos.sgb.gov.br. Setorização de risco: SGB 2018–2019. Suscetibilidade:
IPT/SGB 2013 (escala 1:25.000). Uso livre citando o SGB.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from typing import Any

from shapely.geometry import MultiPolygon, Polygon, mapping, shape
from shapely.validation import make_valid

from quantumco.territory.domain import profile
from quantumco.territory.domain.city import TerritoryCity
from quantumco.territory.domain.records import LayerData, Zone
from quantumco.territory.infrastructure.download import get_json

log = logging.getLogger(__name__)

WFS = "https://geoservicos.sgb.gov.br/geoserver/ows"
LICENSE = "Uso livre citando a fonte: Serviço Geológico do Brasil (SGB/CPRM)"
SUSCEPTIBILITY_NAMES = {
    "suscet_inundacao": "Inundação",
    "suscet_movimento_de_massa": "Movimento de massa",
    "suscet_enxurrada": "Enxurrada",
    "suscet_corrida_de_massa": "Corrida de massa",
}


def _params(type_name: str, municipio: str, uf: str) -> dict[str, Any]:
    # o WFS não tem o código IBGE: o filtro é pelo nome (como o SGB grava) e pela UF, e o
    # resultado é conferido pelo retângulo do município (`_inside`)
    name = municipio.replace("'", "''")
    return {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeNames": f"gestao-territorial:{type_name}",
        "outputFormat": "application/json",
        "srsName": "EPSG:4326",
        "count": 10000,
        "CQL_FILTER": f"municipio='{name}' AND uf='{uf}'",
    }


MARGIN_M = 2000.0  # folga do retângulo do município ao conferir as feições


def _polygonal(geometry: Mapping[str, Any]) -> MultiPolygon | None:
    geom = make_valid(shape(dict(geometry)))
    parts = [g for g in getattr(geom, "geoms", [geom]) if isinstance(g, Polygon | MultiPolygon)]
    polys = [p for g in parts for p in (g.geoms if isinstance(g, MultiPolygon) else [g])]
    return MultiPolygon(polys) if polys else None


def _inside(geometry: Mapping[str, Any], city: TerritoryCity) -> bool:
    try:
        point = shape(dict(geometry)).representative_point()
    except (ValueError, TypeError, AttributeError):
        return False
    return city.contains(point.x, point.y, MARGIN_M)


def _int(value: object) -> int | None:
    try:
        return int(float(str(value).strip()))
    except ValueError:
        return None


class SgbSource:
    name = "sgb-risco"

    def fetch(self, city: TerritoryCity) -> Sequence[LayerData]:
        layers = [self._risk(city)]
        for type_name, label in SUSCEPTIBILITY_NAMES.items():
            layers.append(self._susceptibility(city, type_name, label))
        return layers

    def _features(self, city: TerritoryCity, type_name: str) -> list[Mapping[str, Any]]:
        features: list[Mapping[str, Any]] = []
        names = dict.fromkeys([city.upper_name(), city.upper_name(accents=False)])
        for name in names:  # com acento; se nada vier, sem acento
            data = get_json(WFS, params=_params(type_name, name, city.uf))
            features = list(data.get("features") or [])
            if features:
                break
        inside = [f for f in features if _inside(f.get("geometry") or {}, city)]
        log.info(
            "  %s: %d feições (%d fora do retângulo de %s descartadas)",
            type_name,
            len(inside),
            len(features) - len(inside),
            city.label,
        )
        return inside

    def _risk(self, city: TerritoryCity) -> LayerData:
        zones: list[Zone] = []
        for f in self._features(city, "risco_geologico"):
            p, geom = f.get("properties") or {}, _polygonal(f.get("geometry") or {})
            if geom is None:
                continue
            zones.append(
                Zone(
                    layer=profile.RISK_LAYER,
                    category=str(p.get("grau_risco") or "").strip(),
                    process=str(p.get("tipolo_g1") or "").strip() or "Outro",
                    geometry=mapping(geom),
                    attrs={
                        "sector": p.get("num_setor"),
                        "date": str(p.get("data_setor") or "").rstrip("Z"),
                        "place": p.get("local"),
                        "vulnerability": p.get("grau_vulne"),
                        "buildings": _int(p.get("num_edif")),
                        "households": _int(p.get("num_domi")),
                        "people": _int(p.get("num_pess")),
                    },
                )
            )
        return LayerData(
            layer=profile.RISK_LAYER,
            source="SGB · Setorização de áreas de risco geológico (2018–2019)",
            source_url=f"{WFS}?typeNames=gestao-territorial:risco_geologico",
            license=LICENSE,
            zones=zones,
        )

    def _susceptibility(self, city: TerritoryCity, type_name: str, label: str) -> LayerData:
        zones = []
        for f in self._features(city, type_name):
            p, geom = f.get("properties") or {}, _polygonal(f.get("geometry") or {})
            if geom is None:
                continue
            zones.append(
                Zone(
                    layer=type_name,
                    category=str(p.get("classe") or "").strip(),
                    process=label,
                    geometry=mapping(geom),
                )
            )
        return LayerData(
            layer=type_name,
            source=f"SGB/IPT · Carta de suscetibilidade a {label.lower()} (2013)",
            source_url=f"{WFS}?typeNames=gestao-territorial:{type_name}",
            license=LICENSE,
            zones=zones,
        )
