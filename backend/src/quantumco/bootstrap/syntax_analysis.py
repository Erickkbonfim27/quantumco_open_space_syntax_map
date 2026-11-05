from __future__ import annotations

from quantumco.bootstrap.settings import Settings
from quantumco.platform.postgres import pool
from quantumco.shared_kernel.clock import SystemClock
from quantumco.syntax_analysis.application.queries import GetSyntaxMap
from quantumco.syntax_analysis.application.run_analysis import RunAnalysis
from quantumco.syntax_analysis.infrastructure.postgis_analysis_repository import (
    PostgisAnalysisRepository,
)
from quantumco.syntax_analysis.infrastructure.postgis_network_source import PostgisNetworkSource
from quantumco.syntax_analysis.infrastructure.postgis_syntax_map_reader import (
    PostgisSyntaxMapReader,
)
from quantumco.syntax_analysis.infrastructure.yaml_config import load_analysis_config


def run_analysis_use_case(settings: Settings) -> RunAnalysis:
    # import tardio: o cityseer (Rust + numba) só carrega quando a análise roda, não na API
    from quantumco.syntax_analysis.infrastructure.cityseer_analyzer import (  # noqa: PLC0415
        CityseerAnalyzer,
    )

    database = settings.require_database()
    return RunAnalysis(
        source=PostgisNetworkSource(database),
        analyzer=CityseerAnalyzer(),
        repository=PostgisAnalysisRepository(database),
        config=load_analysis_config(settings.methodology_dir),
        clock=SystemClock(),
    )


def syntax_map_query(settings: Settings) -> GetSyntaxMap:
    return GetSyntaxMap(PostgisSyntaxMapReader(pool(settings.require_database())))
