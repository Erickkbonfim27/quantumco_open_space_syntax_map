"""Overture Maps (https://overturemaps.org): edificações e lugares (comércio e serviços).

Lugares (tema *places*), mesmo release: 8.727 no retângulo, 97% Meta (CDLA Permissive 2.0); entram
os com confiança ≥ 0,5, agrupados pelo primeiro nível da taxonomia. Sem telefone, e-mail ou site.

O tema *buildings* junta OpenStreetMap, Microsoft ML Buildings e Google Open Buildings já
conflacionados (sem prédio duplicado). Em Brusque, no release 2026-10-21.0: 94.366 prédios no
retângulo da grade, 70% Google, 29% Microsoft e 1% OSM; altura em só 8 deles.

Licença do tema: ODbL (por conter OSM; Google entra em CC BY 4.0, compatível). Crédito exigido:
"© OpenStreetMap contributors, Overture Maps Foundation" (docs.overturemaps.org/attribution).

O release é FIXO para a importação ser reproduzível; trocar de release é uma decisão (e um commit).
"""

from __future__ import annotations

import functools
import logging
import time
from collections import Counter
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any, cast

import pyarrow as pa
import pyarrow.parquet as pq
import shapely
from pyproj import Transformer
from shapely import from_wkb
from shapely.geometry import MultiPolygon, Polygon, mapping

from quantumco.territory.domain.city import TerritoryCity
from quantumco.territory.domain.grid import BUFFER_M
from quantumco.territory.domain.profile import BUILDINGS_LAYER
from quantumco.territory.domain.records import Building, LayerData, Place

log = logging.getLogger(__name__)

RELEASE = "2026-10-21.0"
SOURCE_URL = "https://docs.overturemaps.org/guides/buildings/"
BUILDINGS_LICENSE = (
    "ODbL 1.0 · © OpenStreetMap contributors, Overture Maps Foundation "
    "(Microsoft ML Buildings: ODbL; Google Open Buildings: CC BY 4.0)"
)
MIN_AREA_M2 = 10.0  # abaixo disso é quase sempre ruído do modelo (spec F1)


# Criados só no primeiro uso, NUNCA na importação: a CLI importa este módulo e, se o pai do worker
# abrir o banco interno do PROJ antes do fork, o processo filho morre no macOS (SIGSEGV em
# sqlite/os_log ao converter coordenadas; 2026-11-06).
@functools.cache
def _to_utm() -> Transformer:
    return Transformer.from_crs(4326, 31982, always_xy=True)


def city_bbox(city: TerritoryCity) -> tuple[float, float, float, float]:
    """Retângulo WGS84 (oeste, sul, leste, norte): o município com a folga da grade (1 km)."""
    west, south, east, north = city.around(BUFFER_M)
    return round(west, 6), round(south, 6), round(east, 6), round(north, 6)


def download(kind: str, cache_dir: Path, city: TerritoryCity, release: str = RELEASE) -> Path:
    """Baixa um tema do Overture no retângulo da cidade para o cache (uma vez por release)."""
    from overturemaps import core  # noqa: PLC0415  (importa o pyfiglet/click só quando usado)

    cache_dir.mkdir(parents=True, exist_ok=True)
    # a cidade vai no nome: cada uma tem o seu retângulo
    target = cache_dir / f"overture-{kind}-{city.ibge_code}-{release}.parquet"
    bbox = city_bbox(city)
    if target.exists():
        log.info("  cache: %s (%.1f MB)", target.name, target.stat().st_size / 1e6)
        return target
    partial = target.with_suffix(".part")
    for attempt in range(1, 5):
        try:
            started = time.perf_counter()
            reader = core.record_batch_reader(kind, bbox=bbox, release=release, stac=True)
            if reader is None:
                raise RuntimeError(f"Overture sem dados de {kind} no release {release}")
            rows = 0
            with pq.ParquetWriter(partial, reader.schema) as writer:
                for batch in reader:
                    writer.write_batch(batch)
                    rows += batch.num_rows
            partial.replace(target)
            log.info("  baixado %s: %d registros em %.1fs",
                     target.name, rows, time.perf_counter() - started)  # fmt: skip
            return target
        except (OSError, pa.ArrowException) as exc:
            wait = 2**attempt
            log.warning("  falha ao baixar %s (tentativa %d/4): %s; de novo em %ds",
                        kind, attempt, exc, wait)  # fmt: skip
            if attempt == 4:
                raise
            time.sleep(wait)
    raise RuntimeError("inalcançável")


def _primary(sources: Sequence[Mapping[str, Any]] | None) -> Mapping[str, Any]:
    """Fonte da feição inteira (property vazia); senão, a primeira citada."""
    items = list(sources or [])
    whole = [s for s in items if not s.get("property")]
    return (whole or items or [{}])[0]


def normalize_building(row: Mapping[str, Any]) -> tuple[Building | None, str]:
    """Um registro do Overture → Building, ou None e o motivo do descarte."""
    if row.get("is_underground"):
        return None, "subterraneo"
    geom = from_wkb(row["geometry"])
    if not isinstance(geom, Polygon | MultiPolygon) or geom.is_empty:
        return None, "geometria"
    # interleaved=False: a função recebe (x, y) separados; o stub só conhece a forma intercalada
    utm = shapely.transform(geom, cast(Any, _to_utm().transform), interleaved=False)
    if utm.area < MIN_AREA_M2:
        return None, "pequeno"
    source = _primary(row.get("sources"))
    floors = row.get("num_floors")
    height = row.get("height")
    confidence = source.get("confidence")
    return (
        Building(
            building_id=str(row["id"]),
            source=str(source.get("dataset") or "desconhecida"),
            geometry=mapping(geom),
            height_m=float(height) if height is not None else None,
            floors=int(floors) if floors is not None else None,
            klass=row.get("class"),
            confidence=float(confidence) if confidence is not None else None,
        ),
        "ok",
    )


def _rows(path: Path, columns: Sequence[str]) -> Iterator[dict[str, Any]]:
    for batch in pq.ParquetFile(path).iter_batches(batch_size=20_000, columns=list(columns)):
        yield from batch.to_pylist()


class OvertureBuildingsSource:
    name = "overture-edificacoes"

    def __init__(self, cache_dir: Path, release: str = RELEASE) -> None:
        self._cache = cache_dir
        self._release = release

    def fetch(self, city: TerritoryCity) -> Sequence[LayerData]:
        path = download("building", self._cache, city, self._release)
        buildings: list[Building] = []
        outcome: Counter[str] = Counter()
        columns = ("id", "sources", "is_underground", "height", "num_floors", "class", "geometry")
        for row in _rows(path, columns):
            building, why = normalize_building(row)
            outcome[why] += 1
            if building is not None:
                buildings.append(building)
        by_source = Counter(b.source for b in buildings)
        log.info("  edificações: %d aceitas; descartes %s; por fonte %s",
                 len(buildings), dict(outcome - Counter(ok=outcome["ok"])),
                 dict(by_source))  # fmt: skip
        return [
            LayerData(
                layer=BUILDINGS_LAYER,
                source=f"Overture Maps Foundation, tema buildings (release {self._release})",
                source_url=SOURCE_URL,
                license=BUILDINGS_LICENSE,
                buildings=buildings,
                meta={
                    "release": self._release,
                    "bbox": list(city_bbox(city)),
                    "min_area_m2": MIN_AREA_M2,
                    "discarded": {k: v for k, v in outcome.items() if k != "ok"},
                    "by_source": dict(by_source.most_common()),
                    "with_height": sum(1 for b in buildings if b.height_m is not None),
                },
            )
        ]


# ------------------------------------------------------------------ lugares (tema places)

PLACES_LAYER = "lugares"
PLACES_URL = "https://docs.overturemaps.org/guides/places/"
PLACES_LICENSE = (
    "CDLA Permissive 2.0 (Meta, Microsoft) · Apache 2.0 (Foursquare) · CC0 (AllThePlaces) · "
    "Overture Maps Foundation"
)
MIN_PLACE_CONFIDENCE = (
    0.5  # pré-registrado na spec (F2): abaixo disso, muito lugar fechado ou falso
)
# primeiro nível da taxonomia do Overture → grupo no painel (os outros níveis ficam em attrs)
PLACE_GROUPS: Mapping[str, str] = {
    "shopping": "comercio",
    "services_and_business": "servicos",
    "food_and_drink": "alimentacao",
    "lifestyle_services": "beleza_cuidados",
    "travel_and_transportation": "automotivo_transporte",
    "health_care": "saude",
    "cultural_and_historic": "cultura_religiao",
    "education": "educacao",
    "sports_and_recreation": "esporte_lazer",
    "community_and_government": "comunidade_governo",
    "arts_and_entertainment": "arte_entretenimento",
    "lodging": "hospedagem",
}


def normalize_place(row: Mapping[str, Any]) -> tuple[Place | None, str]:
    """Um lugar do Overture → Place (só nome, grupo, categoria, confiança e fonte)."""
    confidence = float(row.get("confidence") or 0.0)
    if confidence < MIN_PLACE_CONFIDENCE:
        return None, "baixa_confianca"
    if (row.get("operating_status") or "open") != "open":
        return None, "fechado"
    hierarchy = list((row.get("taxonomy") or {}).get("hierarchy") or [])
    group = PLACE_GROUPS.get(hierarchy[0]) if hierarchy else None
    if group is None:
        return None, "sem_grupo"
    geom = from_wkb(row["geometry"])
    if geom.geom_type != "Point" or geom.is_empty:
        return None, "geometria"
    source = _primary(row.get("sources"))
    name = (row.get("names") or {}).get("primary")
    return (
        Place(
            layer=PLACES_LAYER,
            kind=group,
            lon=float(geom.x),
            lat=float(geom.y),
            name=str(name)[:160] if name else None,
            attrs={
                "category": hierarchy[-1],
                "confidence": round(confidence, 3),
                "source": source.get("dataset"),
                "license": source.get("license"),
            },
        ),
        "ok",
    )


class OverturePlacesSource:
    name = "overture-lugares"

    def __init__(self, cache_dir: Path, release: str = RELEASE) -> None:
        self._cache = cache_dir
        self._release = release

    def fetch(self, city: TerritoryCity) -> Sequence[LayerData]:
        path = download("place", self._cache, city, self._release)
        places: list[Place] = []
        outcome: Counter[str] = Counter()
        # telefone, e-mail, site e redes sociais nem são lidos (spec, regras herdadas)
        columns = ("id", "names", "confidence", "operating_status", "taxonomy", "sources",
                   "geometry")  # fmt: skip
        for row in _rows(path, columns):
            place, why = normalize_place(row)
            outcome[why] += 1
            if place is not None:
                places.append(place)
        by_group = Counter(p.kind for p in places)
        by_source = Counter(str(p.attrs.get("source")) for p in places)
        log.info("  lugares: %d aceitos; descartes %s; por grupo %s",
                 len(places), {k: v for k, v in outcome.items() if k != "ok"},
                 dict(by_group))  # fmt: skip
        return [
            LayerData(
                layer=PLACES_LAYER,
                source=f"Overture Maps Foundation, tema places (release {self._release})",
                source_url=PLACES_URL,
                license=PLACES_LICENSE,
                places=places,
                meta={
                    "release": self._release,
                    "bbox": list(city_bbox(city)),
                    "min_confidence": MIN_PLACE_CONFIDENCE,
                    "discarded": {k: v for k, v in outcome.items() if k != "ok"},
                    "by_group": dict(by_group.most_common()),
                    "by_source": dict(by_source.most_common()),
                },
            )
        ]
