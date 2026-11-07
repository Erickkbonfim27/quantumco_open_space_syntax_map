"""Imóveis à venda (ADR 0003): impressão digital, quarentena, leitura da glue-api e a carga."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator, Sequence
from dataclasses import replace
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
import requests
from requests.adapters import BaseAdapter

from quantumco.listings.application.import_listings import ImportSaleListings
from quantumco.listings.application.ports import (
    FeatureDisabledError,
    ListingPage,
    MergeResult,
    Rejection,
    RunTally,
    SourceBlockedError,
)
from quantumco.listings.domain.listing import (
    FLAG_GLUE_API,
    InvalidSearchAreaError,
    SaleListing,
    SearchArea,
    problems,
)
from quantumco.listings.infrastructure.glue_api import (
    INCLUDE_FIELDS,
    GlueApiListings,
    parse_item,
    photo_link,
    refusal_reason,
)

BRUSQUE = SearchArea("4202909", "Brusque", "SC")
HOUSE = SaleListing(
    source="grupo-olx",
    listing_id="2701",
    portal="zap",
    city="Brusque",
    property_type="HOME",
    usable_area_m2=120.0,
    bedrooms=3,
    price_brl=650_000.0,
    neighborhood="Centro",
    street="Rua Hercílio Luz",
    address_precision="ALL",
    lon=-48.917,
    lat=-27.098,
    url="https://www.zapimoveis.com.br/imovel/2701",
)


# ---------------------------------------------------------------- domínio


def test_fingerprint_ignores_portal_and_link_but_not_facts() -> None:
    same_on_other_portal = replace(
        HOUSE,
        portal="vivareal",
        url="https://www.vivareal.com.br/x",
        photo_url="https://resizedimgs.vivareal.com/x.jpg",
    )
    assert same_on_other_portal.fingerprint() == HOUSE.fingerprint()
    assert replace(HOUSE, price_brl=640_000.0).fingerprint() != HOUSE.fingerprint()
    assert "url" not in HOUSE.facts()
    assert "price_brl" in HOUSE.facts()


def test_problems_send_bad_data_to_quarantine() -> None:
    assert problems(HOUSE, BRUSQUE) == []
    assert problems(replace(HOUSE, city="brusque"), BRUSQUE) == []  # caixa e acento não importam
    assert problems(replace(HOUSE, city="Guabiruba"), BRUSQUE)
    assert problems(replace(HOUSE, price_brl=0.0), BRUSQUE)
    assert problems(replace(HOUSE, usable_area_m2=-5.0), BRUSQUE)
    assert problems(replace(HOUSE, bedrooms=400), BRUSQUE)
    assert problems(replace(HOUSE, lat=None), BRUSQUE) == ["coordenada pela metade"]
    assert problems(replace(HOUSE, lon=2.35, lat=48.85), BRUSQUE)  # Paris


def test_search_area_comes_from_the_city_registry() -> None:
    itapema = SearchArea("4208302", "Itapema", "SC", bbox=(-48.70, -27.16, -48.55, -27.04))
    assert itapema.state == "Santa Catarina"  # o portal busca pelo nome por extenso
    with pytest.raises(InvalidSearchAreaError):
        SearchArea("42029", "Brusque", "SC")
    with pytest.raises(InvalidSearchAreaError):
        SearchArea("4202909", "Brusque", "XX")


def test_point_must_fall_inside_the_city_when_its_box_is_known() -> None:
    itapema = SearchArea("4208302", "Itapema", "SC", bbox=(-48.70, -27.16, -48.55, -27.04))
    beach = replace(HOUSE, city="Itapema", lon=-48.61, lat=-27.09)
    assert problems(beach, itapema) == []
    in_brusque = replace(HOUSE, city="Itapema")  # ponto de Brusque num anúncio de Itapema
    assert problems(in_brusque, itapema) == ["coordenada fora de Itapema: -48.917, -27.098"]


# ---------------------------------------------------------------- leitura da glue-api


def item(precision: str = "ALL", **listing: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "id": "2701",
        "unitTypes": ["HOME"],
        "usageTypes": ["RESIDENTIAL"],
        "usableAreas": ["120"],
        "bedrooms": [3],
        "parkingSpaces": [],
        "pricingInfos": [
            {"businessType": "RENTAL", "price": "4000"},
            {"businessType": "SALE", "price": "650000", "monthlyCondoFee": "350.5"},
        ],
        "address": {
            "city": "Brusque",
            "neighborhood": "Centro",
            "street": "Rua Hercílio Luz",
            "point": {"lat": -27.0980001, "lon": -48.9170004},
        },
        "displayAddressType": precision,
        # campos que NÃO podem chegar ao banco
        "advertiserContact": {"phones": ["47999990000"]},
        "description": "texto do anunciante",
    }
    body.update(listing)
    return {
        "listing": body,
        "medias": [{"type": "IMAGE", "url": COVER}, {"type": "IMAGE", "url": COVER + "?2"}],
        "link": {"href": "/imovel/2701"},
    }


COVER = "https://resizedimgs.vivareal.com/{action}/{width}x{height}/vr.images.sp/capa.jpg"


def test_parse_item_keeps_facts_and_drops_contact() -> None:
    parsed = parse_item(item(), "zap", "www.zapimoveis.com.br")
    assert parsed is not None
    assert parsed.price_brl == 650_000.0  # o preço de VENDA, não o de aluguel
    assert parsed.condo_fee_brl == 350.5
    assert parsed.usable_area_m2 == 120.0
    assert parsed.bedrooms == 3
    assert parsed.parking_spaces is None
    assert (parsed.lon, parsed.lat) == (-48.917, -27.098)
    assert parsed.url == "https://www.zapimoveis.com.br/imovel/2701"
    assert parsed.photo_url == photo_link(COVER)  # só o link da capa, já pronto
    text = json.dumps(parsed.facts(), ensure_ascii=False)
    assert "47999990000" not in text
    assert "anunciante" not in text


def test_photo_link_fills_the_api_template() -> None:
    template = (
        "https://resizedimgs.vivareal.com/img/vr-listing/eb50/{description}.jpg"
        "?action={action}&amp;dimension={width}x{height}"
    )
    assert photo_link(template) == (
        "https://resizedimgs.vivareal.com/img/vr-listing/eb50/imovel.jpg"
        "?action=fit-in&dimension=640x480"
    )


def test_parse_item_respects_the_address_the_advertiser_shows() -> None:
    street_only = parse_item(item("STREET"), "zap", "www.zapimoveis.com.br")
    assert street_only is not None
    assert street_only.street == "Rua Hercílio Luz"
    assert not street_only.located
    district = parse_item(item("NEIGHBORHOOD"), "zap", "www.zapimoveis.com.br")
    assert district is not None
    assert district.street is None
    assert not district.located
    assert district.neighborhood == "Centro"
    zero = item(address={"city": "Brusque", "point": {"lat": 0, "lon": 0}})
    parsed = parse_item(zero, "zap", "www.zapimoveis.com.br")
    assert parsed is not None
    assert not parsed.located
    assert parse_item({"listing": {}}, "zap", "www.zapimoveis.com.br") is None


Handler = Callable[[requests.PreparedRequest], requests.Response]


class FakeAdapter(BaseAdapter):
    """Transporte em memória para o `requests`: nenhum pedido sai da máquina."""

    def __init__(self, handler: Handler) -> None:
        super().__init__()
        self.handler = handler
        self.calls: list[requests.PreparedRequest] = []

    def send(
        self, request: requests.PreparedRequest, *args: Any, **kwargs: Any
    ) -> requests.Response:
        self.calls.append(request)
        response = self.handler(request)
        response.request = request
        response.url = request.url or ""
        return response

    def close(self) -> None:
        pass


def respond(
    status: int,
    body: object = None,
    *,
    text: str = "",
    content_type: str = "application/json",
    server: str = "",
) -> requests.Response:
    response = requests.Response()
    response.status_code = status
    response.headers["content-type"] = content_type
    if server:
        response.headers["server"] = server
    response._content = (json.dumps(body) if body is not None else text).encode()
    response.encoding = "utf-8"
    return response


def param(request: requests.PreparedRequest, name: str) -> str:
    return parse_qs(urlsplit(request.url or "").query)[name][0]


def cloudflare_403(_: requests.PreparedRequest | None = None) -> requests.Response:
    return respond(
        403,
        text="<title>Attention Required! | Cloudflare</title>",
        content_type="text/html; charset=UTF-8",
        server="cloudflare",
    )


def test_refusal_is_detected_from_status_challenge_or_html() -> None:
    assert refusal_reason(cloudflare_403()) == "HTTP 403 (bloqueio do Cloudflare)"
    assert refusal_reason(respond(200, text="<html>", content_type="text/html")) is not None
    assert refusal_reason(respond(200, {"search": {}})) is None


def source(
    handler: Handler, sleeps: list[float] | None = None, **options: Any
) -> tuple[GlueApiListings, FakeAdapter]:
    adapter = FakeAdapter(handler)
    session = requests.Session()
    session.mount("https://", adapter)
    glue = GlueApiListings(
        page_size=2,
        session=session,
        sleep=(sleeps.append if sleeps is not None else lambda _: None),
        **options,
    )
    return glue, adapter


def test_blocked_source_stops_at_once_without_retrying() -> None:
    glue, adapter = source(cloudflare_403)
    with pytest.raises(SourceBlockedError) as error:
        list(glue.pages(BRUSQUE, max_pages=5))
    assert len(adapter.calls) == 1
    assert error.value.attempts == 1
    headers = adapter.calls[0].headers
    assert "quantumco" in headers["User-Agent"]  # o padrão identifica a quantumco
    assert headers["x-domain"] == "www.zapimoveis.com.br"
    assert headers["Accept-Language"] == "pt-BR,pt;q=0.9"  # os cabeçalhos do data_imob


def page(ids: Sequence[str], total: int) -> dict[str, Any]:
    return {
        "search": {
            "result": {"listings": [item(id=listing_id) for listing_id in ids]},
            "totalCount": total,
        }
    }


def test_user_agent_can_be_set_and_is_sent_as_text() -> None:
    glue, adapter = source(lambda _: respond(200, page([], total=0)), user_agent="poc-pessoal/1.0")
    list(glue.pages(BRUSQUE, max_pages=1))
    assert [call.headers["User-Agent"] for call in adapter.calls] == ["poc-pessoal/1.0"]
    with pytest.raises(ValueError, match="vazio"):
        GlueApiListings(user_agent="  ")


def test_pages_until_the_total_and_retries_only_transient_errors() -> None:
    sleeps: list[float] = []
    answered: list[str] = []

    def handler(request: requests.PreparedRequest) -> requests.Response:
        answered.append(param(request, "from"))
        if len(answered) == 1:
            return respond(502, {"error": "gateway"})
        ids = {"0": ["a", "b"], "2": ["c"]}[param(request, "from")]
        return respond(200, page(ids, total=3))

    glue, adapter = source(handler, sleeps)
    pages = list(glue.pages(BRUSQUE, max_pages=10))
    assert [len(p.listings) for p in pages] == [2, 1]
    assert [p.attempts for p in pages] == [2, 1]
    assert [p.last for p in pages] == [False, True]
    assert answered == ["0", "0", "2"]  # avança por `from`; repetiu o primeiro depois do 502
    last_call = adapter.calls[-1]
    assert param(last_call, "page") == "2"  # `page` coerente com `from`
    assert param(last_call, "includeFields") == INCLUDE_FIELDS
    assert param(last_call, "addressLocationId") == "BR>Santa Catarina>NULL>Brusque"
    assert len(sleeps) == 2  # espera após o 502 e entre as páginas


def test_request_limit_leaves_the_run_incomplete() -> None:
    glue, _ = source(lambda _: respond(200, page(["a", "b"], total=100)))
    pages = list(glue.pages(BRUSQUE, max_pages=2))
    assert len(pages) == 2
    assert not pages[-1].last


def fake_api(prices: dict[str, float | None]) -> Handler:
    """A glue-api em miniatura: filtra por preço (limites inclusivos) e pagina por `from`."""

    def handler(request: requests.PreparedRequest) -> requests.Response:
        query = parse_qs(urlsplit(request.url or "").query)
        low = float(query["priceMin"][0]) if "priceMin" in query else None
        high = float(query["priceMax"][0]) if "priceMax" in query else None
        filtered = low is not None or high is not None
        ids = [
            listing_id
            for listing_id, price in prices.items()
            if not filtered
            or (
                price is not None
                and (low is None or price >= low)
                and (high is None or price <= high)
            )
        ]
        start, size = int(query["from"][0]), int(query["size"][0])
        chunk = [
            item(id=i, pricingInfos=[{"businessType": "SALE", "price": str(prices[i])}])
            for i in ids[start : start + size]
        ]
        return respond(200, {"search": {"result": {"listings": chunk}, "totalCount": len(ids)}})

    return handler


def walk(prices: dict[str, float | None]) -> tuple[list[ListingPage], list[str]]:
    glue, _ = source(fake_api(prices), max_results=4)
    pages = list(glue.pages(BRUSQUE, max_pages=200))
    return pages, [listing.listing_id for p in pages for listing in p.listings]


def test_city_above_the_api_limit_is_split_by_price() -> None:
    prices: dict[str, float | None] = {
        "a": 100_000, "b": 200_000, "c": 300_000, "d": 400_000,
        "e": 5_000_000, "f": 6_000_000, "g": 450_000_000,
    }  # fmt: skip
    pages, seen = walk(prices)
    assert sorted(set(seen)) == sorted(prices)  # todos, mesmo passando do limite de 4 por busca
    assert pages[-1].last  # carga completa: pode marcar removidos
    assert all(p.total == len(prices) for p in pages)


def test_listings_without_price_leave_the_split_run_incomplete() -> None:
    prices: dict[str, float | None] = {
        "a": 100_000, "b": 200_000, "c": 300_000, "d": 400_000, "e": 5_000_000, "sem": None,
    }  # fmt: skip
    pages, seen = walk(prices)
    assert "sem" not in seen
    assert not pages[-1].last  # 1 anúncio fora das faixas: ninguém é marcado como removido


# ---------------------------------------------------------------- a carga (sem banco)


class Flags:
    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled

    def is_enabled(self, name: str) -> bool:
        return self.enabled and name == FLAG_GLUE_API


class Source:
    name = "grupo-olx"

    def __init__(self, pages: Sequence[ListingPage], error: Exception | None = None) -> None:
        self._pages = pages
        self._error = error
        self.called = False

    def pages(self, area: SearchArea, max_pages: int) -> Iterator[ListingPage]:
        self.called = True
        yield from self._pages
        if self._error:
            raise self._error


class Repository:
    def __init__(self) -> None:
        self.merged: list[str] = []
        self.rejected: list[Rejection] = []
        self.removed_called = False
        self.finished: tuple[str, RunTally, str] | None = None
        self.progress_seen: list[int] = []  # páginas gravadas em import_runs durante a carga

    def start_run(self, area: SearchArea, source: str) -> int:
        return 7

    def merge(self, run_id: int, area: SearchArea, listings: Sequence[SaleListing]) -> MergeResult:
        self.merged += [item.listing_id for item in listings]
        return MergeResult(new=len(listings))

    def reject(self, run_id: int, rejections: Sequence[Rejection]) -> None:
        self.rejected += rejections

    def progress(self, run_id: int, tally: RunTally) -> None:
        self.progress_seen.append(tally.pages)

    def mark_removed(self, run_id: int, area: SearchArea, source: str) -> int:
        self.removed_called = True
        return 4

    def finish_run(self, run_id: int, status: str, tally: RunTally, detail: str) -> None:
        self.finished = (status, tally, detail)


def run(flags: Flags, src: Source, repo: Repository, max_pages: int = 40) -> tuple[Repository, Any]:
    use_case = ImportSaleListings(flags, src, repo, flag=FLAG_GLUE_API)
    return repo, use_case(BRUSQUE, max_pages)


def test_flag_off_stops_before_touching_the_source() -> None:
    src = Source([])
    with pytest.raises(FeatureDisabledError):
        run(Flags(False), src, Repository())
    assert not src.called


def test_complete_run_merges_quarantines_and_marks_removed() -> None:
    bad = replace(HOUSE, listing_id="bad", price_brl=-1.0)
    pages = [
        ListingPage([HOUSE, bad], total=3, attempts=1, last=False),
        ListingPage([replace(HOUSE, listing_id="2702", lon=None, lat=None)], 3, 2, last=True),
    ]
    repo, report = run(Flags(True), Source(pages), Repository())
    assert repo.merged == ["2701", "2702"]
    assert [r.listing.listing_id for r in repo.rejected] == ["bad"]
    assert repo.removed_called
    assert report.status == "ok"
    tally = report.tally
    assert (tally.received, tally.new, tally.rejected, tally.removed) == (3, 2, 1, 4)
    assert (tally.located, tally.attempts, tally.complete) == (1, 3, True)
    assert repo.progress_seen == [1, 2]  # o banco acompanha cada página, não só o fim


def test_incomplete_or_blocked_runs_never_mark_removed() -> None:
    partial = [ListingPage([HOUSE], total=500, attempts=1, last=False)]
    repo, report = run(Flags(True), Source(partial), Repository())
    assert not repo.removed_called
    assert not report.tally.complete

    blocked = Source(partial, error=SourceBlockedError("403", attempts=1))
    repo = Repository()
    with pytest.raises(SourceBlockedError):
        run(Flags(True), blocked, repo)
    assert not repo.removed_called
    assert repo.finished is not None
    status, tally, detail = repo.finished
    assert status == "bloqueado"
    assert tally.attempts == 2
    assert "403" in detail
