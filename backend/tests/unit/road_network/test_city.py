from __future__ import annotations

import pytest

from quantumco.road_network.application.ports import BoundaryRef, Municipality
from quantumco.road_network.application.register_city import CityNotFoundError, RegisterCity
from quantumco.road_network.domain.city import (
    City,
    CityStatus,
    UnsupportedCityError,
    sirgas_utm_epsg,
    slugify,
)
from quantumco.road_network.infrastructure.yaml_methodology import YamlMethodology

from .test_build_snapshot import Registry


@pytest.mark.parametrize(
    ("lon", "lat", "epsg"),
    [
        (-48.92, -27.10, 31982),  # Brusque, UTM 22S
        (-48.64, -27.10, 31982),  # Itapema
        (-46.63, -23.55, 31983),  # São Paulo, 23S
        (-60.02, -3.10, 31980),  # Manaus, 20S
        (-60.67, 2.82, 31974),  # Boa Vista, 20N
    ],
)
def test_sirgas_utm_zone_from_the_city_center(lon: float, lat: float, epsg: int) -> None:
    assert sirgas_utm_epsg(lon, lat) == epsg


def test_slug_for_the_map_url() -> None:
    assert slugify("Balneário Camboriú") == "balneario-camboriu"
    assert slugify("Itapema") == "itapema"
    assert slugify("São João d'Aliança") == "sao-joao-d-alianca"


def test_register_picks_crs_and_slug_and_rejects_other_zones_for_now() -> None:
    city = City.register(
        ibge_code="4208302", name="Itapema", uf="sc", osm_relation_id=296608,
        center=(-48.637, -27.0995), buffer_m=7000.0,
    )  # fmt: skip
    assert (city.slug, city.uf, city.crs_epsg, city.status) == (
        "itapema", "SC", 31982, CityStatus.PREPARING,
    )  # fmt: skip
    assert city.study_area().osm_relation_id == 296608
    with pytest.raises(UnsupportedCityError, match="UTM 22S"):
        City.register(
            ibge_code="3550308", name="São Paulo", uf="SP", osm_relation_id=298285,
            center=(-46.63, -23.55), buffer_m=7000.0,
        )  # fmt: skip


class Directory:
    def __init__(self, known: dict[str, Municipality]) -> None:
        self.known = known

    def lookup(self, ibge_code: str) -> Municipality | None:
        return self.known.get(ibge_code)


class Boundaries:
    def __init__(self, known: dict[str, BoundaryRef]) -> None:
        self.known = known
        self.asked: list[str] = []

    def find(self, ibge_code: str) -> BoundaryRef | None:
        self.asked.append(ibge_code)
        return self.known.get(ibge_code)


def register(registry: Registry, methodology: YamlMethodology) -> tuple[RegisterCity, Boundaries]:
    boundaries = Boundaries({"4208302": BoundaryRef(296608, (-48.637, -27.0995))})
    use_case = RegisterCity(
        registry=registry,
        directory=Directory({
            "4208302": Municipality("4208302", "Itapema", "SC"),
            "4218004": Municipality("4218004", "Tijucas", "SC"),
        }),
        boundaries=boundaries,
        methodology=methodology,
    )  # fmt: skip
    return use_case, boundaries


def test_register_city_by_ibge_code(methodology: YamlMethodology) -> None:
    registry = Registry()
    use_case, boundaries = register(registry, methodology)
    city, new = use_case("4208302")
    assert new
    assert registry.get("4208302") == city
    assert (city.name, city.osm_relation_id, city.buffer_m) == ("Itapema", 296608, 7000.0)
    # de novo: nada muda e o OSM nem é consultado
    again, new_again = use_case("4208302")
    assert (again, new_again) == (city, False)
    assert boundaries.asked == ["4208302"]


def test_register_city_needs_ibge_and_osm(methodology: YamlMethodology) -> None:
    use_case, _ = register(Registry(), methodology)
    with pytest.raises(CityNotFoundError, match="IBGE não tem"):
        use_case("9999999")
    with pytest.raises(CityNotFoundError, match="IBGE:GEOCODIGO=4218004"):
        use_case("4218004")
