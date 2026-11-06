"""Busca de endereços sobre o CNEFE 2022 (índice próprio, Q46).

Um item do índice é um número de um logradouro (os vários domicílios de um prédio viram um só
ponto) ou o logradouro inteiro (ponto central dos endereços dele). A busca aceita o jeito que as
pessoas escrevem: sem acento, com abreviações ("r.", "av") e com ou sem número.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass

ABBREVIATIONS = {
    "r": "rua",
    "av": "avenida",
    "avda": "avenida",
    "al": "alameda",
    "trav": "travessa",
    "tv": "travessa",
    "rod": "rodovia",
    "estr": "estrada",
    "pc": "praca",
    "pca": "praca",
    "srv": "servidao",
    "dr": "doutor",
    "prof": "professor",
    "pe": "padre",
    "sta": "santa",
    "sto": "santo",
    "sao": "sao",
    "gov": "governador",
    "pres": "presidente",
    "eng": "engenheiro",
    "cel": "coronel",
}
_STOP = {"de", "da", "do", "das", "dos", "e", "n", "no", "numero"}
_TOKEN = re.compile(r"[a-z0-9]+")


def normalize(text: str) -> str:
    """Minúsculas, sem acento, abreviações expandidas, espaços simples."""
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    words = [ABBREVIATIONS.get(w, w) for w in _TOKEN.findall(plain)]
    return " ".join(words)


@dataclass(frozen=True, slots=True)
class AddressQuery:
    words: tuple[str, ...]  # palavras do nome do logradouro (sem número)
    number: int | None

    @classmethod
    def parse(cls, text: str) -> AddressQuery:
        words = normalize(text).split()
        number = None
        # o número é o ÚLTIMO termo, se for só dígitos: "rua x 120"; "rua 7 de setembro" não tem
        if len(words) > 1 and words[-1].isdigit() and len(words[-1]) <= 5:
            number = int(words[-1])
            words = words[:-1]
        kept = tuple(w for w in words if w not in _STOP and not (w.isdigit() and len(w) == 8))
        return cls(words=kept, number=number)

    @property
    def searchable(self) -> bool:
        return sum(len(w) for w in self.words) >= 3


@dataclass(frozen=True, slots=True)
class AddressHit:
    street: str  # "Rua Hercílio Luz"
    number: int | None  # None = o logradouro inteiro
    locality: str | None
    cep: str | None
    lon: float
    lat: float
    units: int  # endereços do CNEFE representados por este ponto
    exact: bool = False  # o número pedido existe

    @property
    def label(self) -> str:
        head = self.street if self.number is None else f"{self.street}, {self.number}"
        tail = " · ".join(x for x in (self.locality, _cep(self.cep)) if x)
        return f"{head} · {tail}" if tail else head


def _cep(cep: str | None) -> str | None:
    if not cep or len(cep) != 8 or not cep.isdigit():
        return cep
    return f"{cep[:5]}-{cep[5:]}"


def rank(candidates: Sequence[AddressHit], query: AddressQuery, limit: int = 8) -> list[AddressHit]:
    """Ordena: logradouro que começa com a busca primeiro; com número, o mais próximo dele."""
    joined = " ".join(query.words)

    def matches(key: str) -> bool:
        # cada palavra começa uma palavra do logradouro; número só bate inteiro ("1" ≠ "13")
        parts = key.split()
        return all(
            any(p == w if w.isdigit() else p.startswith(w) for p in parts) for w in query.words
        )

    def street_score(hit: AddressHit) -> tuple[int, int, int]:
        key = normalize(hit.street)
        name = key.split(" ", 1)[1] if " " in key else key  # sem o tipo (rua, avenida…)
        exact = sum(w in key.split() for w in query.words)  # palavras inteiras pesam mais
        starts = 0 if key.startswith(joined) or name.startswith(joined) else 1
        return -exact, starts, len(key)

    by_street: dict[str, list[AddressHit]] = {}
    for hit in candidates:
        if matches(normalize(hit.street)):
            by_street.setdefault(hit.street, []).append(hit)
    streets = sorted(by_street, key=lambda s: street_score(by_street[s][0]))
    out: list[AddressHit] = []
    for street in streets:
        hits = by_street[street]
        whole = [h for h in hits if h.number is None]
        numbered = [h for h in hits if h.number is not None]
        if query.number is not None and numbered:
            best = min(numbered, key=lambda h: abs((h.number or 0) - (query.number or 0)))
            exact = best.number == query.number
            out.append(
                AddressHit(best.street, best.number, best.locality, best.cep, best.lon, best.lat,
                           best.units, exact)
            )  # fmt: skip
        elif whole:
            out.append(whole[0])
        if len(out) >= limit:
            break
    return out
