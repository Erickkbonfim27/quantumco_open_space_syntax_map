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


class MovableClock:
    """Relógio que o teste avança (limites de tempo entre e-mails, validade dos links)."""

    def __init__(self) -> None:
        self.current = datetime(2026, 11, 8, 3, 0, tzinfo=UTC)

    def now(self) -> datetime:
        return self.current

    def advance(self, **delta: float) -> None:
        from datetime import timedelta  # noqa: PLC0415

        self.current += timedelta(**delta)
