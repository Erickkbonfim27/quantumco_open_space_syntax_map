"""Perfil territorial de um polígono: regras de agregação, sem I/O.

Dados por setor censitário entram por INTERPOLAÇÃO DASIMÉTRICA: cada setor contribui com a fração
dos seus domicílios (endereços do CNEFE 2022, com coordenada) que cai dentro do polígono. Só quando
o setor não tem domicílio georreferenciado é que se usa a fração de área. Isso evita, por exemplo,
dar população a um morro vazio só porque ele ocupa metade da área do setor.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from quantumco.territory.domain.records import Number

# Atributos do setor (nomes nossos; o adaptador do IBGE traduz das variáveis V0xxxx).
PEOPLE = "people"
HOUSEHOLDS = "households"  # domicílios particulares ocupados (V0007)
DWELLINGS = "dwellings"  # domicílios particulares, ocupados ou não (V0003)
HEADS = "heads"  # responsáveis por domicílio (base da renda)
INCOME_MEAN = "income_mean"
INCOME_MEDIAN = "income_median"

# Entorno dos domicílios (Censo 2022): domicílios ocupados em faces COM o item / base pesquisada.
STREETSCAPE_BASE = "sc_base"
STREETSCAPE_ITEMS = (
    "paved",
    "drain",
    "lighting",
    "sidewalk",
    "ramp",
    "obstacle",
    "trees",
    "trees_5",
    "bus_stop",
    "bike",
    "heavy_traffic",
)

RISK_LAYER = "risco"
RISK_ORDER = ("Baixo", "Médio", "Alto", "Muito alto")
SUSCEPTIBILITY_LAYERS = (
    "suscet_inundacao",
    "suscet_movimento_de_massa",
    "suscet_enxurrada",
    "suscet_corrida_de_massa",
)
SUSCEPTIBILITY_ORDER = ("Baixa", "Média", "Alta")


@dataclass(frozen=True, slots=True)
class TractOverlap:
    code: str
    attrs: Mapping[str, Number]
    area_share: float  # fração da ÁREA do setor dentro do polígono (0..1)
    addresses_in: int  # domicílios do CNEFE do setor dentro do polígono
    addresses_all: int  # domicílios do CNEFE do setor

    @property
    def share(self) -> float:
        if self.addresses_all > 0:
            return self.addresses_in / self.addresses_all
        return self.area_share

    @property
    def weighting(self) -> str:
        return "domicilios" if self.addresses_all > 0 else "area"


@dataclass(frozen=True, slots=True)
class ZoneOverlap:
    layer: str
    category: str
    process: str
    attrs: Mapping[str, Any]
    area_in_m2: float
    area_total_m2: float

    @property
    def share(self) -> float:
        return self.area_in_m2 / self.area_total_m2 if self.area_total_m2 > 0 else 0.0


def _num(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    try:
        return float(str(value).replace(",", "."))
    except ValueError:
        return None


def population(overlaps: Sequence[TractOverlap], area_km2: float) -> dict[str, Any]:
    people = households = dwellings = heads = income_sum = 0.0
    suppressed = 0
    means: list[float] = []
    for t in overlaps:
        w = t.share
        if w <= 0:
            continue
        people += w * (_num(t.attrs.get(PEOPLE)) or 0.0)
        households += w * (_num(t.attrs.get(HOUSEHOLDS)) or 0.0)
        dwellings += w * (_num(t.attrs.get(DWELLINGS)) or 0.0)
        h, mean = _num(t.attrs.get(HEADS)), _num(t.attrs.get(INCOME_MEAN))
        if h is None or mean is None:
            suppressed += 1
            continue
        heads += w * h
        income_sum += w * h * mean
        if w >= 0.05:
            means.append(mean)
    tracts = [t for t in overlaps if t.share > 0]
    return {
        "people": round(people),
        "households": round(households),
        "density_km2": round(people / area_km2, 1) if area_km2 > 0 else None,
        # não ocupados = vagos + uso ocasional (veraneio etc.), na definição do IBGE
        "unoccupied_share": round(1 - households / dwellings, 4) if dwellings > 0 else None,
        "income_mean": round(income_sum / heads, 2) if heads > 0 else None,
        "income_heads": round(heads),
        "income_tract_range": [round(min(means), 2), round(max(means), 2)] if means else None,
        "tracts": len(tracts),
        "tracts_income_suppressed": suppressed,
        "weighting": sorted({t.weighting for t in tracts}),
    }


def streetscape(overlaps: Sequence[TractOverlap]) -> dict[str, Any] | None:
    """Fração (0..1) dos domicílios cujas faces de quadra têm cada item; None fora da pesquisa."""
    base = 0.0
    totals: dict[str, float] = defaultdict(float)
    for t in overlaps:
        b = _num(t.attrs.get(STREETSCAPE_BASE))
        if not b or t.share <= 0:
            continue
        base += t.share * b
        for item in STREETSCAPE_ITEMS:
            totals[item] += t.share * (_num(t.attrs.get(f"sc_{item}")) or 0.0)
    if base <= 0:
        return None
    shares: dict[str, Any] = {item: round(totals[item] / base, 4) for item in STREETSCAPE_ITEMS}
    shares["households_surveyed"] = round(base)
    return shares


def risk(overlaps: Iterable[ZoneOverlap]) -> dict[str, Any]:
    zones = [z for z in overlaps if z.layer == RISK_LAYER and z.area_in_m2 > 0]
    area_by: dict[str, float] = defaultdict(float)
    processes: dict[str, float] = defaultdict(float)
    people = households = 0.0
    for z in zones:
        area_by[z.category] += z.area_in_m2 / 1e6
        processes[z.process] += z.area_in_m2 / 1e6
        people += z.share * (_num(z.attrs.get("people")) or 0.0)
        households += z.share * (_num(z.attrs.get("households")) or 0.0)
    worst = max(
        (z.category for z in zones if z.category in RISK_ORDER),
        key=RISK_ORDER.index,
        default=None,
    )
    return {
        "sectors": len(zones),
        "worst": worst,
        "area_km2": {k: round(area_by[k], 4) for k in RISK_ORDER if area_by.get(k)},
        "processes_km2": {
            k: round(v, 4) for k, v in sorted(processes.items(), key=lambda kv: -kv[1])
        },
        "people": round(people),
        "households": round(households),
    }


def susceptibility(overlaps: Iterable[ZoneOverlap], area_m2: float) -> dict[str, dict[str, float]]:
    """Fração da área do polígono em cada classe, por processo (cartas IPT/SGB 2013)."""
    by_layer: dict[str, dict[str, float]] = {name: {} for name in SUSCEPTIBILITY_LAYERS}
    for z in overlaps:
        if z.layer not in by_layer or area_m2 <= 0:
            continue
        cell = by_layer[z.layer]
        cell[z.category] = cell.get(z.category, 0.0) + z.area_in_m2 / area_m2
    return {
        layer: {k: round(min(v, 1.0), 4) for k, v in classes.items()}
        for layer, classes in by_layer.items()
    }
