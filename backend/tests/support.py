"""Apoio comum aos testes (sem banco)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

METHODOLOGY_V1 = Path(__file__).resolve().parents[1] / "methodology" / "v1"

# coordenadas reais de Brusque em UTM 22S, para a reprojeção dar lon/lat plausíveis
X0, Y0 = 700_000.0, 7_000_000.0


class FixedClock:
    def now(self) -> datetime:
        return datetime(2026, 11, 8, 3, 0, tzinfo=UTC)
