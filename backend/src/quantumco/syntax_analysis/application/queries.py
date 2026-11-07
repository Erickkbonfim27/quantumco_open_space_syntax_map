from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class SyntaxMap:
    """Trechos com geometria (WGS84) e medidas, prontos para o navegador."""

    analysis_id: str
    manifest: Mapping[str, Any]
    links_geojson: bytes


class SyntaxMapReader(Protocol):
    def current(self, ibge_code: str) -> SyntaxMap | None: ...


class NoAnalysisError(LookupError):
    pass


class GetSyntaxMap:
    def __init__(self, reader: SyntaxMapReader) -> None:
        self._reader = reader

    def __call__(self, ibge_code: str) -> SyntaxMap:
        current = self._reader.current(ibge_code)
        if current is None:
            raise NoAnalysisError(
                f"a cidade {ibge_code} não tem análise sintática; rode `quantumco analysis run`"
            )
        return current


@dataclass(frozen=True, slots=True)
class ScenarioMap:
    name: str
    manifest: Mapping[str, Any]
    links_geojson: bytes


class ScenarioReader(Protocol):
    def list(self) -> list[Mapping[str, Any]]: ...

    def get(self, name: str) -> ScenarioMap | None: ...


class NoScenarioError(LookupError):
    pass


class GetScenario:
    def __init__(self, reader: ScenarioReader) -> None:
        self._reader = reader

    def list(self) -> list[Mapping[str, Any]]:
        return self._reader.list()

    def __call__(self, name: str) -> ScenarioMap:
        found = self._reader.get(name)
        if found is None:
            raise NoScenarioError(f"cenário {name!r} não existe")
        return found


class PolygonStatsReader(Protocol):
    def stats(self, ibge_code: str, ring: list[tuple[float, float]]) -> Mapping[str, Any] | None:
        """Camadas N1 (território) e N5 (rede) para um polígono em (lon, lat), na cidade."""
        ...


class GetPolygonStats:
    def __init__(self, reader: PolygonStatsReader) -> None:
        self._reader = reader

    def __call__(self, ibge_code: str, ring: list[tuple[float, float]]) -> Mapping[str, Any]:
        result = self._reader.stats(ibge_code, ring)
        if result is None:
            raise NoAnalysisError(f"a cidade {ibge_code} não tem análise sintática publicada")
        return result
