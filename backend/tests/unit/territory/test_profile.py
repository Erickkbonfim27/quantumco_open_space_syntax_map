from __future__ import annotations

import pytest

from quantumco.territory.domain import profile
from quantumco.territory.domain.profile import TractOverlap, ZoneOverlap


def tract(attrs: dict[str, float | None], *, area: float, inside: int, total: int) -> TractOverlap:
    return TractOverlap("t", attrs, area_share=area, addresses_in=inside, addresses_all=total)


def test_share_is_dasymetric_with_area_fallback() -> None:
    assert tract({}, area=0.9, inside=10, total=40).share == pytest.approx(0.25)
    empty = tract({}, area=0.3, inside=0, total=0)
    assert empty.share == pytest.approx(0.3)
    assert empty.weighting == "area"


def test_population_sums_shares_and_weights_income_by_heads() -> None:
    rich = tract(
        {"people": 100, "households": 40, "dwellings": 50, "heads": 40, "income_mean": 9000},
        area=1, inside=10, total=10,
    )  # fmt: skip
    poor = tract(
        {"people": 300, "households": 100, "dwellings": 100, "heads": 100, "income_mean": 2000},
        area=1, inside=5, total=10,
    )  # fmt: skip
    out = profile.population([rich, poor], area_km2=2.0)
    assert out["people"] == 250  # 100 + 0,5 × 300
    assert out["households"] == 90
    assert out["density_km2"] == 125.0
    # (40×9000 + 50×2000) / 90
    assert out["income_mean"] == pytest.approx(5111.11, abs=0.01)
    assert out["unoccupied_share"] == pytest.approx(1 - 90 / 100)


def test_suppressed_income_is_counted_not_zeroed() -> None:
    hidden = tract({"people": 10, "heads": None, "income_mean": None}, area=1, inside=1, total=1)
    out = profile.population([hidden], area_km2=1.0)
    assert out["income_mean"] is None
    assert out["tracts_income_suppressed"] == 1


def test_streetscape_is_share_of_surveyed_households() -> None:
    a = tract({"sc_base": 100, "sc_sidewalk": 80, "sc_lighting": 100}, area=1, inside=1, total=1)
    rural = tract({"sc_base": None}, area=1, inside=1, total=1)
    out = profile.streetscape([a, rural])
    assert out is not None
    assert out["sidewalk"] == pytest.approx(0.8)
    assert out["lighting"] == pytest.approx(1.0)
    assert profile.streetscape([rural]) is None


def test_risk_scales_people_by_area_and_keeps_worst_grade() -> None:
    zones = [
        ZoneOverlap("risco", "Alto", "Deslizamento", {"people": 40}, 5_000, 10_000),
        ZoneOverlap("risco", "Muito alto", "Inundação", {"people": 10}, 1_000, 1_000),
        ZoneOverlap("suscet_inundacao", "Alta", "Inundação", {}, 1_000, 1_000),
    ]
    out = profile.risk(zones)
    assert out["sectors"] == 2
    assert out["people"] == 30
    assert out["worst"] == "Muito alto"


FULL = {
    "age_0_14": 20, "age_15_29": 30, "age_30_59": 40, "age_60p": 10,
    "pop_15p": 80, "literate_15p": 76,
    "dppo": 40, "water_network": 40, "sewer_network": 10, "garbage_collected": 38,
}  # fmt: skip


def test_demography_weights_ages_literacy_and_sanitation_by_share() -> None:
    a = tract(FULL, area=1, inside=10, total=10)  # inteiro dentro
    b = tract(FULL | {"sewer_network": 30}, area=1, inside=5, total=10)  # metade dentro
    out = profile.demography([a, b])
    assert out is not None
    assert out["ages"] == {"age_0_14": 0.2, "age_15_29": 0.3, "age_30_59": 0.4, "age_60p": 0.1}
    assert out["literacy_15p"] == 0.95
    assert out["pop_15p"] == 120
    # esgoto: (10 + 0,5 × 30) / (40 + 0,5 × 40) = 25 / 60
    assert out["sanitation"]["sewer_network"] == pytest.approx(25 / 60, abs=1e-4)
    assert out["permanent_households"] == 60


def test_demography_drops_suppressed_tracts_from_numerator_and_base() -> None:
    ok = tract(FULL, area=1, inside=1, total=1)
    hidden = tract(FULL | {"literate_15p": None}, area=1, inside=1, total=1)
    out = profile.demography([ok, hidden])
    assert out is not None
    assert out["literacy_15p"] == 0.95  # o setor sigiloso não puxa a taxa para baixo
    assert out["tracts_suppressed"]["literacy"] == 1
    assert profile.demography([tract({"people": 10}, area=1, inside=1, total=1)]) is None


def test_susceptibility_is_share_of_polygon_area() -> None:
    zones = [ZoneOverlap("suscet_inundacao", "Alta", "Inundação", {}, 250_000, 900_000)]
    out = profile.susceptibility(zones, area_m2=1_000_000)
    assert out["suscet_inundacao"] == {"Alta": 0.25}
    assert out["suscet_enxurrada"] == {}
