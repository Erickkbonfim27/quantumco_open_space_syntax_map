"""API HTTP (adaptador de entrada). Rodar: `uv run quantumco serve`.

Em produção: `uvicorn quantumco.entrypoints.api.app:create_app --factory`.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from quantumco.bootstrap.platform import build_platform
from quantumco.bootstrap.road_network import current_network_query
from quantumco.bootstrap.settings import Settings, load_env_file
from quantumco.bootstrap.syntax_analysis import scenario_query, syntax_map_query
from quantumco.bootstrap.territory import territory_profile_query
from quantumco.entrypoints.api.platform_routes import platform_router
from quantumco.entrypoints.api.territory_routes import territory_router
from quantumco.identity.application.auth import Authentication
from quantumco.road_network.application.queries import (
    GetCurrentNetwork,
    NoSnapshotError,
    PublishedNetwork,
)
from quantumco.scenarios.application.workspaces import Workspaces
from quantumco.syntax_analysis.application.queries import (
    GetPolygonStats,
    GetScenario,
    GetSyntaxMap,
    NoAnalysisError,
    NoScenarioError,
)
from quantumco.territory.application.queries import GetPolygonProfile

log = logging.getLogger(__name__)

GEOJSON = "application/geo+json"
CACHE_CONTROL = "public, max-age=300"


def create_app(
    settings: Settings | None = None,
    *,
    network_query: GetCurrentNetwork | None = None,
    syntax_query: GetSyntaxMap | None = None,
    scenarios: GetScenario | None = None,
    platform: tuple[Authentication, Workspaces, GetPolygonStats] | None = None,
    territory: GetPolygonProfile | None = None,
) -> FastAPI:
    if settings is None:
        load_env_file()
        settings = Settings.from_env()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )

    app = FastAPI(
        title="quantumco API",
        description="Mapa sintático aberto de Brusque-SC",
        version="0.1.0",
    )
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_origins),
            allow_methods=["GET", "POST", "PATCH", "DELETE"],
            allow_headers=["*"],
            allow_credentials=True,
        )

    query = network_query or current_network_query(settings)

    @app.exception_handler(NoSnapshotError)
    async def no_snapshot(_: Request, error: NoSnapshotError) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(error)})

    @app.exception_handler(NoScenarioError)
    async def no_scenario(_: Request, error: NoScenarioError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(error)})

    @app.exception_handler(NoAnalysisError)
    async def no_analysis(_: Request, error: NoAnalysisError) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(error)})

    @app.get("/health", tags=["operação"])
    def health() -> dict[str, Any]:
        try:
            network = query()
        except NoSnapshotError:
            return {"status": "ok", "snapshot": None}
        return {"status": "ok", "snapshot": network.snapshot_id}

    app.include_router(_network_router(query), prefix="/api/v1/network")
    app.include_router(
        _syntax_router(syntax_query or syntax_map_query(settings)), prefix="/api/v1/syntax"
    )
    app.include_router(
        _scenario_router(scenarios or scenario_query(settings)), prefix="/api/v1/scenarios"
    )
    auth, workspaces, polygon_stats = platform or build_platform(settings)
    app.include_router(
        platform_router(auth, workspaces, polygon_stats, secure=settings.cookie_secure),
        prefix="/api/v1",
    )
    app.include_router(
        territory_router(territory or territory_profile_query(settings)), prefix="/api/v1"
    )
    return app


def _scenario_router(query: GetScenario) -> APIRouter:
    router = APIRouter(tags=["cenários"])

    @router.get("")
    def list_scenarios() -> list[dict[str, Any]]:
        return [dict(item) for item in query.list()]

    @router.get("/{name}/manifest")
    def scenario_manifest(name: str) -> dict[str, Any]:
        return dict(query(name).manifest)

    @router.get("/{name}/links", response_class=Response)
    def scenario_links(name: str) -> Response:
        return Response(content=query(name).links_geojson, media_type=GEOJSON)

    return router


def _syntax_router(query: GetSyntaxMap) -> APIRouter:
    router = APIRouter(tags=["análise sintática"])

    @router.get("/manifest")
    def manifest() -> JSONResponse:
        current = query()
        return JSONResponse(
            content=dict(current.manifest),
            headers={"ETag": f'"{current.analysis_id}"', "Cache-Control": CACHE_CONTROL},
        )

    @router.get("/links", response_class=Response)
    def links(request: Request) -> Response:
        current = query()
        etag = f'"{current.analysis_id}"'
        headers = {"ETag": etag, "Cache-Control": CACHE_CONTROL}
        if request.headers.get("if-none-match") == etag:
            return Response(status_code=304, headers=headers)
        return Response(content=current.links_geojson, media_type=GEOJSON, headers=headers)

    return router


def _network_router(query: GetCurrentNetwork) -> APIRouter:
    router = APIRouter(tags=["rede viária"])

    def cached(request: Request, network: PublishedNetwork, body: bytes, media: str) -> Response:
        etag = f'"{network.snapshot_id}"'
        headers = {"ETag": etag, "Cache-Control": CACHE_CONTROL}
        if request.headers.get("if-none-match") == etag:
            return Response(status_code=304, headers=headers)
        return Response(content=body, media_type=media, headers=headers)

    @router.get("/manifest")
    def manifest(request: Request) -> Response:
        network = query()
        return JSONResponse(
            content=dict(network.manifest),
            headers={"ETag": f'"{network.snapshot_id}"', "Cache-Control": CACHE_CONTROL},
        )

    @router.get("/links", response_class=Response)
    def links(request: Request) -> Response:
        network = query()
        return cached(request, network, network.links_geojson, GEOJSON)

    @router.get("/municipality", response_class=Response)
    def municipality(request: Request) -> Response:
        network = query()
        return cached(request, network, network.municipality_geojson, GEOJSON)

    return router
