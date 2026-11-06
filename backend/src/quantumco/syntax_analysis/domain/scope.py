"""Alcance do cálculo de um cenário: quais raios recalcular e em que parte da rede.

Sem o raio n, o recálculo fica restrito à região que a edição pode alterar, e o resultado é
EXATO (igual ao da cidade inteira), não uma aproximação. No raio r:
- a integração (NAIN) de uma reta só muda se a edição estiver a até r dela;
- a escolha (NACH) de uma reta w soma os caminhos de origem s a destino t (d(s,t) ≤ r) que
  passam por w; se a edição muda algum desses caminhos, ela está a até r de s, e w está a até
  r de s: logo w está a até 2r da edição.
Então:
- trechos de SAÍDA: os que têm alguma parte a até 2r de uma geometria alterada;
- retas de ORIGEM ("live" no motor): as que estão a até r de algum trecho de saída. Assim, as
  duas pontas de todo caminho que passa por um trecho de saída são origens, e a escolha sai
  certa seja qual for o lado de onde o motor conta o par;
- o resto da rede entra só como caminho; os demais trechos ficam com o valor publicado.
Distância em linha reta ≤ distância pela rede: a região euclidiana nunca é menor que a necessária.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from shapely import STRtree
from shapely.geometry import LineString

from quantumco.syntax_analysis.domain.segmentation import Coords, Link, Piece

# Atalhos da tela (a ordem é a da metodologia; "n" = cidade inteira).
PRESETS: dict[str, tuple[str, ...]] = {
    "caminhada": ("400", "800"),
    "bairro": ("400", "800", "1200", "2000"),
    "cidade": ("400", "800", "1200", "2000", "n"),
}
DEFAULT_PRESET = "bairro"


class InvalidScopeError(ValueError):
    pass


def check_radii(keys: Sequence[str] | None, available: Sequence[str]) -> tuple[str, ...]:
    """Raios pedidos → na ordem da metodologia; vazio ou desconhecido é recusado."""
    if keys is None:
        keys = PRESETS[DEFAULT_PRESET]
    unknown = sorted(set(keys) - set(available))
    if unknown:
        raise InvalidScopeError(f"raio desconhecido: {', '.join(unknown)}")
    chosen = tuple(k for k in available if k in set(keys))
    if not chosen:
        raise InvalidScopeError("escolha pelo menos um raio")
    return chosen


def is_local(keys: Sequence[str]) -> bool:
    return "n" not in keys


@dataclass(frozen=True, slots=True)
class Region:
    output: frozenset[str]  # ids de trecho (como reportados) que recebem valor recalculado
    live: tuple[bool, ...]  # por reta, na ordem de `pieces`: True = origem no motor

    @property
    def live_count(self) -> int:
        return sum(self.live)


def affected_region(
    links: Sequence[Link],
    report_ids: Sequence[str],
    pieces: Sequence[Piece],
    changed: Sequence[Coords],
    radius_m: float,
) -> Region:
    """`links[i]` reporta como `report_ids[i]`; `changed` são as geometrias alteradas pela edição
    (trechos removidos, ruas novas, metades de trechos divididos) e `radius_m` o MAIOR raio."""
    if radius_m <= 0:
        raise InvalidScopeError("raio da região precisa ser positivo")
    if not changed:
        return Region(frozenset(), tuple(False for _ in pieces))
    link_lines = [LineString(link.coords) for link in links]
    changed_lines = [LineString(c) for c in changed]
    near = STRtree(link_lines).query(changed_lines, predicate="dwithin", distance=2 * radius_m)
    output = frozenset(report_ids[int(i)] for i in np.unique(near[1]))
    # todas as partes de um trecho de saída (as duas metades de um trecho dividido)
    output_lines = [line for line, rid in zip(link_lines, report_ids, strict=True) if rid in output]
    piece_lines = [LineString([p.start, p.end]) for p in pieces]
    reach = STRtree(piece_lines).query(output_lines, predicate="dwithin", distance=radius_m)
    live_index = set(np.unique(reach[1]).tolist())
    return Region(output, tuple(i in live_index for i in range(len(pieces))))
