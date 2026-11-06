"""Edições da rede viária num cenário do usuário ("e se…").

São só a intenção do usuário, em lon/lat (WGS84), como a tela desenha. O recálculo
(Análise Sintática) recebe estas edições traduzidas pelo bootstrap e decide o encaixe na rede:

- remover: a via deixa de existir;
- interditar: para a sintaxe é o mesmo que remover (a via sai do grafo), mas aparece como
  interdição no mapa e no relatório (obra, bloqueio, rua fechada);
- nova via: linha desenhada; as PONTAS se conectam à rede (até 30 m);
- redesenhar: troca o traçado de uma via existente (remove a original e cria a nova).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from quantumco.scenarios.domain.common import BOUNDS, InvalidWorkspaceError

MAX_EDITS = 200
MAX_LINE_VERTICES = 500
MIN_LINE_LENGTH_DEG = 1e-5  # ~1 m: duas pontas no mesmo lugar não formam uma rua

Line = tuple[tuple[float, float], ...]  # (lon, lat)


class EditKind(StrEnum):
    REMOVE = "remove"
    CLOSE = "close"
    ADD = "add"
    REROUTE = "reroute"


@dataclass(frozen=True, slots=True)
class NetworkEdit:
    kind: EditKind
    link_id: str | None = None  # remover, interditar e redesenhar
    coords: Line | None = None  # nova via e redesenhar
    label: str = ""  # nome livre dado pelo usuário (ex.: "ponte nova")

    def __post_init__(self) -> None:
        needs_link = self.kind in (EditKind.REMOVE, EditKind.CLOSE, EditKind.REROUTE)
        needs_line = self.kind in (EditKind.ADD, EditKind.REROUTE)
        if needs_link and not (self.link_id and self.link_id.strip()):
            raise InvalidWorkspaceError("Escolha a via que será alterada.")
        if not needs_link and self.link_id is not None:
            raise InvalidWorkspaceError("Uma via nova não aponta para via existente.")
        if needs_line:
            self._check_line()
        elif self.coords is not None:
            raise InvalidWorkspaceError("Remover ou interditar não leva traçado.")
        object.__setattr__(self, "label", " ".join(self.label.split())[:80])

    def _check_line(self) -> None:
        coords = self.coords or ()
        if len(coords) < 2:
            raise InvalidWorkspaceError("A via precisa de pelo menos 2 pontos.")
        if len(coords) > MAX_LINE_VERTICES:
            raise InvalidWorkspaceError(f"No máximo {MAX_LINE_VERTICES} pontos por via.")
        west, south, east, north = BOUNDS
        if not all(west <= x <= east and south <= y <= north for x, y in coords):
            raise InvalidWorkspaceError("A via precisa estar em Brusque ou no entorno.")
        (x0, y0), (x1, y1) = coords[0], coords[-1]
        if abs(x1 - x0) + abs(y1 - y0) < MIN_LINE_LENGTH_DEG and len(coords) == 2:
            raise InvalidWorkspaceError("A via é curta demais.")
        clean = tuple((round(float(x), 7), round(float(y), 7)) for x, y in coords)
        object.__setattr__(self, "coords", clean)

    @property
    def removes(self) -> str | None:
        """Id da via existente que sai da rede (remover, interditar ou redesenhar)."""
        return self.link_id if self.kind != EditKind.ADD else None

    def to_json(self) -> dict[str, Any]:
        data: dict[str, Any] = {"type": self.kind.value}
        if self.link_id is not None:
            data["link_id"] = self.link_id
        if self.coords is not None:
            data["coords"] = [list(c) for c in self.coords]
        if self.label:
            data["label"] = self.label
        return data

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> NetworkEdit:
        try:
            kind = EditKind(str(data.get("type")))
        except ValueError as error:
            raise InvalidWorkspaceError("Tipo de edição desconhecido.") from error
        raw = data.get("coords")
        coords: Line | None = None
        if raw is not None:
            try:
                coords = tuple((float(p[0]), float(p[1])) for p in raw)
            except (TypeError, ValueError, IndexError) as error:
                raise InvalidWorkspaceError("Traçado inválido.") from error
        link = data.get("link_id")
        return cls(
            kind=kind,
            link_id=None if link is None else str(link),
            coords=coords,
            label=str(data.get("label") or ""),
        )


def check_edits(edits: Sequence[NetworkEdit]) -> None:
    """Regras do conjunto: limite e no máximo uma alteração por via existente."""
    if len(edits) > MAX_EDITS:
        raise InvalidWorkspaceError(f"No máximo {MAX_EDITS} edições por cenário.")
    seen: set[str] = set()
    for edit in edits:
        link = edit.removes
        if link is None:
            continue
        if link in seen:
            raise InvalidWorkspaceError(f"A via #{link} já tem uma alteração neste cenário.")
        seen.add(link)
