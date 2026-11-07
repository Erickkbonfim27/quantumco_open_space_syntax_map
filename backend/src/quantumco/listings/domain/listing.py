"""Imóvel à venda: só os fatos do anúncio que o mapa usa (sem contato, texto nem foto)."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from dataclasses import asdict, dataclass

from quantumco.shared_kernel.city import InvalidCityCodeError, city_code

FLAG_GLUE_API = "listings_glue_api"

# Os portais buscam pelo nome do estado por extenso; o cadastro de cidades guarda a UF.
STATE_NAMES = {
    "AC": "Acre", "AL": "Alagoas", "AP": "Amapá", "AM": "Amazonas", "BA": "Bahia",
    "CE": "Ceará", "DF": "Distrito Federal", "ES": "Espírito Santo", "GO": "Goiás",
    "MA": "Maranhão", "MT": "Mato Grosso", "MS": "Mato Grosso do Sul", "MG": "Minas Gerais",
    "PA": "Pará", "PB": "Paraíba", "PR": "Paraná", "PE": "Pernambuco", "PI": "Piauí",
    "RJ": "Rio de Janeiro", "RN": "Rio Grande do Norte", "RS": "Rio Grande do Sul",
    "RO": "Rondônia", "RR": "Roraima", "SC": "Santa Catarina", "SP": "São Paulo",
    "SE": "Sergipe", "TO": "Tocantins",
}  # fmt: skip

# Fora da impressão digital: mudam sem o imóvel mudar (o mesmo anúncio visto pelo ZAP ou pelo
# Viva Real tem portal e link diferentes; o link da foto muda com o servidor de imagens).
_NOT_FACTS = frozenset({"source", "listing_id", "portal", "url", "photo_url"})

# Faixas plausíveis. Fora delas o anúncio vai para a quarentena e não sobrescreve o que já temos.
MAX_PRICE_BRL = 500_000_000.0
MAX_AREA_M2 = 1_000_000.0
MAX_ROOMS = 50
BRAZIL_BBOX = (-74.0, -34.0, -34.0, 5.5)  # oeste, sul, leste, norte


class InvalidSearchAreaError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class SearchArea:
    """Onde buscar: a cidade do cadastro (ADR 0002), identificada pelo código IBGE.

    `bbox` é o retângulo do município (lon/lat) com uma folga; sem ele (cidade ainda sem rede
    publicada) a coordenada só é conferida contra o Brasil.
    """

    ibge_code: str
    city: str  # "Itapema"
    uf: str  # "SC"
    bbox: tuple[float, float, float, float] | None = None  # oeste, sul, leste, norte

    def __post_init__(self) -> None:
        try:
            city_code(self.ibge_code)
        except InvalidCityCodeError as exc:
            raise InvalidSearchAreaError(str(exc)) from exc
        if not self.city.strip():
            raise InvalidSearchAreaError("informe o nome da cidade")
        if self.uf not in STATE_NAMES:
            raise InvalidSearchAreaError(f"UF desconhecida: {self.uf!r}")

    @property
    def state(self) -> str:
        """Nome do estado por extenso, como os portais buscam ("Santa Catarina")."""
        return STATE_NAMES[self.uf]


@dataclass(frozen=True, slots=True)
class SaleListing:
    source: str  # provedor: "grupo-olx"
    listing_id: str
    portal: str | None = None  # zap | vivareal
    city: str | None = None  # como veio no endereço do anúncio
    property_type: str | None = None
    usage_type: str | None = None
    usable_area_m2: float | None = None
    total_area_m2: float | None = None
    bedrooms: int | None = None
    bathrooms: int | None = None
    suites: int | None = None
    parking_spaces: int | None = None
    price_brl: float | None = None
    condo_fee_brl: float | None = None
    iptu_brl: float | None = None
    neighborhood: str | None = None
    street: str | None = None
    address_precision: str | None = None  # ALL | STREET | NEIGHBORHOOD
    lon: float | None = None
    lat: float | None = None
    url: str | None = None
    photo_url: str | None = None  # só o link da capa; a imagem fica no servidor do portal

    @property
    def located(self) -> bool:
        return self.lon is not None and self.lat is not None

    def facts(self) -> dict[str, object]:
        """Os fatos do anúncio: o que vai para o histórico e para a impressão digital."""
        return {key: value for key, value in asdict(self).items() if key not in _NOT_FACTS}

    def fingerprint(self) -> str:
        """sha256 dos fatos em JSON canônico: muda só quando o anúncio muda de verdade."""
        canonical = json.dumps(
            self.facts(), sort_keys=True, ensure_ascii=False, separators=(",", ":")
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _norm(text: str) -> str:
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return " ".join(plain.lower().split())


def problems(listing: SaleListing, area: SearchArea) -> list[str]:
    """Motivos para pôr o anúncio na quarentena (lista vazia = válido)."""
    out: list[str] = []
    if listing.city and _norm(listing.city) != _norm(area.city):
        out.append(f"cidade {listing.city!r} fora da busca ({area.city})")
    if listing.price_brl is not None and not 0 < listing.price_brl <= MAX_PRICE_BRL:
        out.append(f"preço fora da faixa: {listing.price_brl}")
    for label, area_m2 in (
        ("área útil", listing.usable_area_m2),
        ("área total", listing.total_area_m2),
    ):
        if area_m2 is not None and not 0 < area_m2 <= MAX_AREA_M2:
            out.append(f"{label} fora da faixa: {area_m2}")
    for label, count in (
        ("quartos", listing.bedrooms),
        ("banheiros", listing.bathrooms),
        ("suítes", listing.suites),
        ("vagas", listing.parking_spaces),
    ):
        if count is not None and not 0 <= count <= MAX_ROOMS:
            out.append(f"{label} fora da faixa: {count}")
    if (listing.lon is None) != (listing.lat is None):
        out.append("coordenada pela metade")
    elif listing.lon is not None and listing.lat is not None:
        west, south, east, north = area.bbox or BRAZIL_BBOX
        if not (west <= listing.lon <= east and south <= listing.lat <= north):
            where = area.city if area.bbox else "Brasil"
            out.append(f"coordenada fora de {where}: {listing.lon}, {listing.lat}")
    return out
