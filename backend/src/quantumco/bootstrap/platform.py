from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from quantumco.bootstrap.identity import build_avatar_store, build_mailer
from quantumco.bootstrap.scenario_runs import build_runs
from quantumco.bootstrap.settings import Settings
from quantumco.identity.application.account import AccountEmails
from quantumco.identity.application.auth import Authentication
from quantumco.identity.application.profile import Profile
from quantumco.identity.infrastructure.argon2_hasher import Argon2Hasher
from quantumco.identity.infrastructure.email_templates import BrandedAccountMessages
from quantumco.identity.infrastructure.postgis_identity import (
    PostgisSessionStore,
    PostgisTokenStore,
    PostgisUserRepository,
)
from quantumco.platform.postgres import shared_pool
from quantumco.scenarios.application.runs import ScenarioRuns
from quantumco.scenarios.application.workspaces import Workspaces
from quantumco.scenarios.infrastructure.postgis_workspaces import PostgisWorkspaceRepository
from quantumco.shared_kernel.clock import SystemClock
from quantumco.syntax_analysis.application.queries import GetPolygonStats
from quantumco.syntax_analysis.infrastructure.postgis_polygon_stats import PostgisPolygonStats
from quantumco.syntax_analysis.infrastructure.postgis_scenarios import PostgisScenarioRepository


@dataclass(frozen=True, slots=True)
class Platform:
    """O que a API da Plataforma usa: conta, perfil, cenários, fila e camadas."""

    auth: Authentication
    profile: Profile
    workspaces: Workspaces
    runs: ScenarioRuns
    polygon_stats: GetPolygonStats
    forget_result: Callable[[str], None]  # apaga o resultado de um cenário apagado
    account: AccountEmails  # confirmação de e-mail, troca de e-mail e de senha por link
    public_base_url: str = "https://quantumco.com.br"  # base dos links nos e-mails


def build_platform(settings: Settings) -> Platform:
    database = settings.require_database()
    shared = shared_pool(database)
    clock = SystemClock()
    users = PostgisUserRepository(shared)
    sessions = PostgisSessionStore(shared)
    hasher = Argon2Hasher()
    workspaces = Workspaces(repository=PostgisWorkspaceRepository(shared), clock=clock)
    account = AccountEmails(
        users=users,
        tokens=PostgisTokenStore(shared),
        sessions=sessions,
        hasher=hasher,
        mailer=build_mailer(settings),
        messages=BrandedAccountMessages(),
        clock=clock,
    )
    return Platform(
        auth=Authentication(users=users, hasher=hasher, sessions=sessions, clock=clock),
        profile=Profile(users=users, avatars=build_avatar_store(settings), clock=clock),
        workspaces=workspaces,
        runs=build_runs(settings, workspaces),
        polygon_stats=GetPolygonStats(PostgisPolygonStats(shared)),
        forget_result=PostgisScenarioRepository(database).delete,
        account=account,
        public_base_url=settings.public_base_url,
    )
