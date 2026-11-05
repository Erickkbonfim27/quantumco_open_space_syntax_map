from __future__ import annotations

from quantumco.bootstrap.settings import Settings
from quantumco.identity.application.auth import Authentication
from quantumco.identity.infrastructure.argon2_hasher import Argon2Hasher
from quantumco.identity.infrastructure.postgis_identity import (
    PostgisSessionStore,
    PostgisUserRepository,
)
from quantumco.platform.postgres import shared_pool
from quantumco.scenarios.application.workspaces import Workspaces
from quantumco.scenarios.infrastructure.postgis_workspaces import PostgisWorkspaceRepository
from quantumco.shared_kernel.clock import SystemClock
from quantumco.syntax_analysis.application.queries import GetPolygonStats
from quantumco.syntax_analysis.infrastructure.postgis_polygon_stats import PostgisPolygonStats


def build_platform(settings: Settings) -> tuple[Authentication, Workspaces, GetPolygonStats]:
    shared = shared_pool(settings.require_database())
    clock = SystemClock()
    auth = Authentication(
        users=PostgisUserRepository(shared),
        hasher=Argon2Hasher(),
        sessions=PostgisSessionStore(shared),
        clock=clock,
    )
    workspaces = Workspaces(repository=PostgisWorkspaceRepository(shared), clock=clock)
    return auth, workspaces, GetPolygonStats(PostgisPolygonStats(shared))
