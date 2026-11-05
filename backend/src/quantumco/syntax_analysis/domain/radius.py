from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True, order=True)
class Radius:
    """Raio métrico da análise. `meters=None` é o raio n (sem corte)."""

    meters: int | None

    def __post_init__(self) -> None:
        if self.meters is not None and self.meters <= 0:
            raise ValueError("raio deve ser positivo")

    @property
    def key(self) -> str:
        return "n" if self.meters is None else str(self.meters)

    @property
    def is_global(self) -> bool:
        return self.meters is None

    def distance_m(self, n_distance_m: int) -> int:
        return n_distance_m if self.meters is None else self.meters
