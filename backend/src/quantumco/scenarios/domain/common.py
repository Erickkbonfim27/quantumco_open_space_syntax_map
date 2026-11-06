"""Regras comuns do contexto de cenários do usuário."""

from __future__ import annotations

# limites de Brusque + faixa de 7 km (graus, WGS84) — geometrias fora disso não fazem sentido
BOUNDS = (-49.12, -27.33, -48.70, -26.93)


class InvalidWorkspaceError(ValueError):
    pass
