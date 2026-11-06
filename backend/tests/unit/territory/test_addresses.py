from __future__ import annotations

from quantumco.territory.application.queries import SearchAddresses
from quantumco.territory.domain.addresses import AddressHit, AddressQuery, normalize

STREET = "Rua Hercilio Luz"


def hit(number: int | None, street: str = STREET) -> AddressHit:
    return AddressHit(street, number, "Centro I", "88350300", -48.91, -27.09, 1)


class Index:
    def __init__(self, hits: list[AddressHit]) -> None:
        self.hits = hits
        self.words: list[str] = []

    def candidates(self, words: list[str], limit: int = 600) -> list[AddressHit]:
        self.words = list(words)
        return [h for h in self.hits if all(w in normalize(h.street) for w in words)]


def test_normalize_and_parse() -> None:
    assert normalize("R. Hercílio  Luz") == "rua hercilio luz"
    assert normalize("Av. Pres. Getúlio") == "avenida presidente getulio"
    query = AddressQuery.parse("r hercilio luz, 120")
    assert query.words == ("rua", "hercilio", "luz")
    assert query.number == 120
    seven = AddressQuery.parse("rua 7 de setembro")
    assert (seven.words, seven.number) == (("rua", "7", "setembro"), None)
    assert AddressQuery.parse("rua 7 de setembro 300").number == 300
    assert not AddressQuery.parse("ru").searchable


def test_nearest_number_and_whole_street() -> None:
    index = Index([hit(None), hit(100), hit(118), hit(130), hit(None, "Rua Luz Divina")])
    search = SearchAddresses(index)
    first = search("hercilio luz 120")[0]
    assert (first.number, first.exact) == (118, False)
    assert first.label == "Rua Hercilio Luz, 118 · Centro I · 88350-300"
    assert search("hercilio luz 130")[0].exact
    whole = search("rua hercilio")
    assert whole[0].number is None
    assert index.words == ["rua", "hercilio"]
    assert search("x") == []
