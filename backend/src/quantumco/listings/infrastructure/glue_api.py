"""Fonte `ListingSource` pela glue-api do Grupo OLX: a API dos sites ZAP Imóveis e Viva Real.

Não é pública nem documentada (docs/adr/0003). Fica atrás da flag `listings_glue_api`, para prova
de conceito pessoal, sem redistribuir os dados. Regras:
- o User-Agent padrão identifica a quantumco; `QC_LISTINGS_USER_AGENT` (no `.env`, fora do
  repositório) troca o valor por decisão do dono;
- pede como o data_imob pedia: biblioteca `requests` e os mesmos cabeçalhos. Em 06/11/2026, com
  os mesmos cabeçalhos, a glue-api respondeu 200 pelo `requests` e 403 do Cloudflare pelo `httpx`;
- nada além disso: sem imitar a conexão de um navegador, sem navegador automatizado, sem proxies,
  sem resolver desafios;
- respeita o limite da API: no máximo 1.500 anúncios por busca (`from` ≥ 1.500 dá 404, "Page is
  above acceptable limit"). Cidade maior é dividida em faixas de preço, o mesmo filtro do site;
- recusa da fonte (401/403/407/429, desafio do Cloudflare, HTML no lugar de JSON) → para na hora
  com `SourceBlockedError`, sem nova tentativa;
- só repete erro passageiro do servidor (500/502/503/504 sem página do Cloudflare), com espera
  crescente;
- pede devagar (um pedido a cada `delay_s`) e só os fatos do mapa e o link da foto de capa:
  nada de contato, texto do anúncio ou cópia das fotos.

Paginação: a API ignora `page` (06/11: as páginas 2 a 50 repetiam a 1); quem avança é `from`.
Mandamos os dois, coerentes entre si.
"""

from __future__ import annotations

import logging
import math
import time
from collections.abc import Callable, Generator, Iterator, Mapping, Sequence
from typing import Any
from urllib.parse import urljoin

import requests

from quantumco.listings.application.ports import ListingPage, SourceBlockedError
from quantumco.listings.domain.listing import SaleListing, SearchArea

SOURCE = "grupo-olx"
PORTALS: dict[str, tuple[str, str]] = {
    # portal: (endpoint, domínio que a API usa para escolher o índice e montar o link)
    "zap": ("https://glue-api.zapimoveis.com.br/v2/listings", "www.zapimoveis.com.br"),
    "vivareal": ("https://glue-api.vivareal.com/v2/listings", "www.vivareal.com.br"),
}
USER_AGENT = "quantumco/0.1 (mapa sintatico aberto; +https://quantumco.com.br)"
TIMEOUT_S = 30.0
MAX_RESULTS = 1_500  # por busca; a API recusa `from` ≥ 1.500
PRICE_CEILING = 1_000_000_000  # R$ 1 bi: teto das faixas de preço
# primeiros cortes: quase todo imóvel fica abaixo de R$ 2 mi; começar daqui poupa medições
FIRST_CUTS = (2_000_000, 20_000_000)
_MIN_BAND_BRL = 1_000  # faixa mais estreita que isso não se divide mais
# tamanho da foto no link guardado (o modelo da API traz {action} e {width}x{height})
PHOTO_ACTION = "fit-in"
PHOTO_SIZE = "640x480"

# fatos do mapa e as fotos (guardamos só o link da capa); sem advertiserContact, account
# (telefones), description nem title
# Os mesmos campos do teste que devolveu o link do anúncio, inclusive o `page` no fim (o
# contexto da página, que a API usa para montar `link.href`). As cargas 10 e 11 vieram sem link:
# a 10 pedia menos campos; a 11 já tinha os campos, mas não o `page`.
INCLUDE_FIELDS = (
    "search(result(listings(listing(displayAddressType,amenities,usableAreas,constructionStatus,"
    "listingType,unitTypes,propertyType,unitSubTypes,id,portal,parkingSpaces,address,suites,"
    "publicationType,bathrooms,usageTypes,totalAreas,bedrooms,pricingInfos,showPrice,status,"
    "business),medias,link)),totalCount),page"
)
_REFUSED = frozenset({401, 403, 407, 429})
_TRANSIENT = frozenset({500, 502, 503, 504})

Filters = Mapping[str, int]
Band = tuple[Filters, Mapping[str, Any], int, int]  # filtros, 1ª página, tentativas, total

log = logging.getLogger(__name__)


class GlueApiError(RuntimeError):
    pass


class _AboveLimitError(GlueApiError):
    """A API recusou o deslocamento (passou do limite de anúncios por busca)."""


def refusal_reason(response: requests.Response) -> str | None:
    """Por que a resposta é uma recusa da fonte (None = não é recusa)."""
    status = response.status_code
    content_type = response.headers.get("content-type", "")
    looks_cloudflare = (
        "cloudflare" in response.headers.get("server", "").lower()
        or "cloudflare" in response.text[:4000].lower()
    )
    if response.headers.get("cf-mitigated"):
        return f"HTTP {status} com desafio do Cloudflare"
    if status in _REFUSED:
        return f"HTTP {status}" + (" (bloqueio do Cloudflare)" if looks_cloudflare else "")
    if status in _TRANSIENT and "text/html" in content_type and looks_cloudflare:
        return f"HTTP {status} com página do Cloudflare"
    if status == 200 and "json" not in content_type:
        return f"página {content_type or 'sem tipo'} no lugar de JSON (desafio anti-robô)"
    return None


def _search(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    return _mapping(payload.get("search"))


def _total(payload: Mapping[str, Any]) -> int:
    return int(_search(payload).get("totalCount") or 0)


def _items(payload: Mapping[str, Any]) -> Sequence[Any]:
    items = _mapping(_search(payload).get("result")).get("listings")
    return items if isinstance(items, list) else []


class GlueApiListings:
    def __init__(
        self,
        portal: str = "zap",
        *,
        page_size: int = 30,  # o mesmo do site e do data_imob (com 50 a API respondeu 400)
        delay_s: float = 3.0,
        max_attempts: int = 3,
        max_results: int = MAX_RESULTS,
        session: requests.Session | None = None,
        sleep: Callable[[float], None] = time.sleep,
        user_agent: str = USER_AGENT,
    ) -> None:
        if portal not in PORTALS:
            raise ValueError(f"portal desconhecido: {portal!r} (use {', '.join(PORTALS)})")
        if not user_agent.strip():
            raise ValueError("User-Agent vazio")
        self._portal = portal
        self._endpoint, self._domain = PORTALS[portal]
        self._page_size = page_size
        self._delay_s = delay_s
        self._max_attempts = max_attempts
        self._max_results = max_results
        self._sleep = sleep
        self._session = session or requests.Session()
        # em todo pedido; os mesmos cabeçalhos do data_imob
        self._headers = {
            "User-Agent": user_agent.strip(),
            "Accept-Language": "pt-BR,pt;q=0.9",
            "x-domain": self._domain,
        }
        self._left = 0  # pedidos que ainda cabem nesta carga
        self._made = 0

    @property
    def name(self) -> str:
        return SOURCE

    # ------------------------------------------------------------ percorrer a cidade

    def pages(self, area: SearchArea, max_pages: int) -> Iterator[ListingPage]:
        """Todos os anúncios da cidade. `max_pages` limita os pedidos (sondagens incluídas).

        A última página sai com `last=True` só se a carga cobriu tudo o que a API diz ter.
        """
        self._left, self._made = max_pages, 0
        if not self._spend():
            return
        first, attempts = self._request(area, 0, {})
        total = _total(first)
        complete = True
        if total <= self._max_results:
            bands: list[Band] = [({}, first, attempts, total)]
        else:
            bands, complete = self._plan(area, total)
            if not bands:  # sem faixas (filtro ignorado ou sem pedidos): os primeiros 1.500
                bands = [({}, first, attempts, total)]
            covered = sum(band[3] for band in bands)
            log.info("busca dividida em %d faixas de preço: %d de %d anúncios",
                     len(bands), covered, total)  # fmt: skip
            if covered < total:
                log.warning("%d anúncios fora das faixas de preço (sem preço?): carga incompleta, "
                            "ninguém será marcado como removido", total - covered)  # fmt: skip
                complete = False
        for index, (filters, band_first, band_attempts, band_total) in enumerate(bands):
            final = complete and index == len(bands) - 1
            done = yield from self._walk(
                area,
                filters=filters,
                payload=band_first,
                attempts=band_attempts,
                band_total=band_total,
                total=total,
                final=final,
            )
            if not done:
                return

    def _plan(self, area: SearchArea, total: int) -> tuple[list[Band], bool]:
        """Divide o preço ao meio até cada faixa caber no limite da API."""
        # o filtro precisa funcionar: acima de R$ 500 mi não pode estar a cidade inteira
        log.info("  %d anúncios, acima do limite de %d por busca: medindo faixas de preço",
                 total, self._max_results)  # fmt: skip
        if not self._spend():
            return [], False
        top, _ = self._request(area, 0, {"priceMin": PRICE_CEILING // 2 + 1})
        if _total(top) >= total:
            log.warning("a API ignorou o filtro de preço: só os primeiros %d anúncios",
                        self._max_results)  # fmt: skip
            return [], False
        bands: list[Band] = []
        complete = True
        edges = [0, *FIRST_CUTS, PRICE_CEILING]
        starts = [edges[0], *(edge + 1 for edge in edges[1:-1])]
        pending = list(zip(starts, edges[1:], strict=True))[::-1]  # a mais barata sai primeiro
        while pending:
            low, high = pending.pop()
            if not self._spend():
                log.warning("limite de pedidos atingido ao dividir as faixas de preço")
                return bands, False
            filters = {"priceMin": low, "priceMax": high}
            payload, attempts = self._request(area, 0, filters)
            count = _total(payload)
            log.info("  faixa R$ %s a R$ %s: %d anúncios%s", f"{low:,}".replace(",", "."),
                     f"{high:,}".replace(",", "."), count,
                     " → divide" if count > self._max_results else "")  # fmt: skip
            if count <= self._max_results or high - low < _MIN_BAND_BRL:
                if count > self._max_results:
                    log.warning("faixa R$ %d–%d com %d anúncios não se divide mais: só %d",
                                low, high, count, self._max_results)  # fmt: skip
                    complete = False
                if count:
                    bands.append((filters, payload, attempts, count))
                continue
            middle = (low + high) // 2
            pending += [(middle + 1, high), (low, middle)]  # a mais barata primeiro
        return bands, complete

    def _walk(
        self,
        area: SearchArea,
        *,
        filters: Filters,
        payload: Mapping[str, Any],
        attempts: int,
        band_total: int,
        total: int,
        final: bool,
    ) -> Generator[ListingPage, None, bool]:
        """Percorre uma faixa por `from`; devolve se a faixa veio inteira."""
        limit = min(band_total, self._max_results)
        offset = 0
        while True:
            items = _items(payload)
            offset += len(items)
            band_done = not items or offset >= limit
            whole = band_done and offset >= band_total
            listings = [
                parsed
                for parsed in (parse_item(item, self._portal, self._domain) for item in items)
                if parsed is not None
            ]
            yield ListingPage(listings, total=total, attempts=attempts, last=final and whole)
            if band_done:
                return whole
            if not self._spend():
                log.warning("limite de pedidos atingido: carga incompleta")
                return False
            try:
                payload, attempts = self._request(area, offset, filters)
            except _AboveLimitError:
                return False

    # ------------------------------------------------------------ um pedido

    def _spend(self) -> bool:
        if self._left <= 0:
            return False
        self._left -= 1
        return True

    def _request(
        self, area: SearchArea, offset: int, filters: Filters
    ) -> tuple[Mapping[str, Any], int]:
        if self._made:
            self._sleep(self._delay_s)
        self._made += 1
        params: dict[str, str | int] = {
            "business": "SALE",
            "listingType": "USED",
            "categoryPage": "RESULT",
            "addressCity": area.city,
            "addressState": area.state,
            "addressLocationId": f"BR>{area.state}>NULL>{area.city}",
            "from": offset,
            "page": offset // self._page_size + 1,
            "size": self._page_size,
            "includeFields": INCLUDE_FIELDS,
            **filters,
        }
        for attempt in range(1, self._max_attempts + 1):
            try:
                response = self._session.get(
                    self._endpoint, params=params, headers=self._headers, timeout=TIMEOUT_S
                )
            except (requests.ConnectionError, requests.Timeout) as exc:
                if attempt == self._max_attempts:
                    raise GlueApiError(f"sem resposta após {attempt} tentativas: {exc}") from exc
                log.warning("glue-api: %s (tentativa %d de %d)", exc, attempt, self._max_attempts)
                self._sleep(self._delay_s * 2**attempt)
                continue
            refusal = refusal_reason(response)
            if refusal:
                raise SourceBlockedError(
                    f"{self._domain} recusou o acesso: {refusal}. Nada foi contornado.",
                    attempts=attempt,
                )
            if response.status_code in _TRANSIENT and attempt < self._max_attempts:
                log.warning("glue-api: HTTP %d (tentativa %d de %d)",
                            response.status_code, attempt, self._max_attempts)  # fmt: skip
                self._sleep(self._delay_s * 2**attempt)
                continue
            if response.status_code != 200:
                body = " ".join(response.text[:300].split())
                error = _AboveLimitError if "acceptable limit" in body else GlueApiError
                raise error(
                    f"HTTP {response.status_code} em {self._endpoint} "
                    f"(from {offset}, {self._page_size} por página, {dict(filters)}): "
                    f"{body or 'sem corpo'}"
                )
            payload = response.json()
            return (payload if isinstance(payload, Mapping) else {}), attempt
        raise GlueApiError("tentativas esgotadas")


# ---------------------------------------------------------------- leitura do anúncio


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _first(value: object) -> object:
    if isinstance(value, list):
        return value[0] if value else None
    return value


def _text(value: object) -> str | None:
    value = _first(value)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _number(value: object) -> float | None:
    value = _first(value)
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(str(value).replace(",", "."))
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _integer(value: object) -> int | None:
    number = _number(value)
    return int(number) if number is not None and number.is_integer() else None


def _money(value: object) -> float | None:
    number = _number(value)
    return round(number, 2) if number is not None else None


def _sale_pricing(value: object) -> Mapping[str, Any]:
    infos = [info for info in value if isinstance(info, Mapping)] if isinstance(value, list) else []
    for info in infos:
        if info.get("businessType") == "SALE":
            return info
    return infos[0] if infos else {}


def photo_link(template: str) -> str:
    """O modelo da API ({description}, {action}, {width}x{height}) → link pronto para o mapa."""
    return (
        template.replace("&amp;", "&")
        .replace("{description}", "imovel")
        .replace("{action}", PHOTO_ACTION)
        .replace("{width}x{height}", PHOTO_SIZE)
    )


def _cover(value: object) -> str | None:
    """Link da primeira foto (só o link: a imagem continua no servidor do portal)."""
    for media in value if isinstance(value, list) else []:
        url = _text(_mapping(media).get("url"))
        if url and url.startswith("http"):
            return photo_link(url)
    return None


def parse_item(item: Mapping[str, Any], portal: str, domain: str) -> SaleListing | None:
    """Um item da busca → fatos do anúncio. Respeita o endereço que o anunciante escolheu mostrar:
    ponto só com o endereço completo (ALL); rua com ALL ou STREET; com NEIGHBORHOOD, só o bairro.
    """
    listing = _mapping(item.get("listing"))
    listing_id = _text(listing.get("id"))
    if listing_id is None:
        return None
    address = _mapping(listing.get("address"))
    precision = _text(listing.get("displayAddressType"))
    point = _mapping(address.get("point"))
    lon, lat = _number(point.get("lon")), _number(point.get("lat"))
    full = precision == "ALL" and lon is not None and lat is not None and (lon, lat) != (0.0, 0.0)
    price = _sale_pricing(listing.get("pricingInfos"))
    href = _text(_mapping(item.get("link")).get("href"))
    return SaleListing(
        source=SOURCE,
        listing_id=listing_id,
        portal=portal,
        city=_text(address.get("city")),
        property_type=_text(listing.get("unitTypes")),
        usage_type=_text(listing.get("usageTypes")),
        usable_area_m2=_number(listing.get("usableAreas")),
        total_area_m2=_number(listing.get("totalAreas")),
        bedrooms=_integer(listing.get("bedrooms")),
        bathrooms=_integer(listing.get("bathrooms")),
        suites=_integer(listing.get("suites")),
        parking_spaces=_integer(listing.get("parkingSpaces")),
        price_brl=_money(price.get("price")),
        condo_fee_brl=_money(price.get("monthlyCondoFee")),
        iptu_brl=_money(price.get("yearlyIptu")),
        neighborhood=_text(address.get("neighborhood")),
        street=_text(address.get("street")) if precision in {"ALL", "STREET"} else None,
        address_precision=precision,
        lon=round(lon, 6) if full and lon is not None else None,
        lat=round(lat, 6) if full and lat is not None else None,
        url=urljoin(f"https://{domain}", href) if href else None,
        photo_url=_cover(item.get("medias")),
    )
