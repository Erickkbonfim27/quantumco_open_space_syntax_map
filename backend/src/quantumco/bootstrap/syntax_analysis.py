from __future__ import annotations

from quantumco.bootstrap.settings import Settings
from quantumco.shared_kernel.clock import SystemClock
from quantumco.syntax_analysis.application.queries import GetSyntaxMap
from quantumco.syntax_analysis.application.run_analysis import RunAnalysis
from quantumco.syntax_analysis.infrastructure.file_analysis_repository import (
    FileAnalysisRepository,
)
from quantumco.syntax_analysis.infrastructure.file_syntax_map_reader import FileSyntaxMapReader
from quantumco.syntax_analysis.infrastructure.gpkg_network_source import GpkgNetworkSource
from quantumco.syntax_analysis.infrastructure.yaml_config import load_analysis_config


def run_analysis_use_case(settings: Settings) -> RunAnalysis:
    # import tardio: o cityseer (Rust + numba) só carrega quando a análise roda, não na API
    from quantumco.syntax_analysis.infrastructure.cityseer_analyzer import (  # noqa: PLC0415
        CityseerAnalyzer,
    )

    return RunAnalysis(
        source=GpkgNetworkSource(settings.data_dir / "snapshots"),
        analyzer=CityseerAnalyzer(),
        repository=FileAnalysisRepository(settings.data_dir / "analyses"),
        config=load_analysis_config(settings.methodology_dir),
        clock=SystemClock(),
    )


def syntax_map_query(settings: Settings) -> GetSyntaxMap:
    return GetSyntaxMap(
        FileSyntaxMapReader(settings.data_dir / "snapshots", settings.data_dir / "analyses")
    )
