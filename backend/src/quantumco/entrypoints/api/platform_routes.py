"""Rotas da Plataforma: autenticação, cenários do usuário e estatísticas de polígonos."""

# sem `from __future__ import annotations`: o FastAPI precisa resolver CurrentUser (local)

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from quantumco.identity.application.auth import Authentication, AuthError
from quantumco.identity.domain.user import User
from quantumco.scenarios.application.workspaces import WorkspaceNotFoundError, Workspaces
from quantumco.scenarios.domain.workspace import (
    InvalidWorkspaceError,
    Measure,
    Status,
    Workspace,
)
from quantumco.syntax_analysis.application.queries import GetPolygonStats

COOKIE = "qc_session"
SESSION_SECONDS = 30 * 24 * 3600

Coordinates = Annotated[list[tuple[float, float]], Field(min_length=3, max_length=500)]


class SignUpBody(BaseModel):
    name: str = Field(max_length=200)
    email: str = Field(max_length=254)
    organization: str | None = Field(default=None, max_length=200)
    password: str = Field(max_length=256)


class LogInBody(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=256)


class WorkspaceBody(BaseModel):
    name: str = Field(default="", max_length=200)
    measure: Measure = Measure.NAIN


class WorkspacePatch(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    measure: Measure | None = None
    status: Status | None = None


class PolygonBody(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    coordinates: Coordinates


class StatsBody(BaseModel):
    coordinates: Coordinates


def _user_json(user: User) -> dict[str, Any]:
    return {
        "id": str(user.user_id),
        "name": user.name,
        "email": str(user.email),
        "organization": user.organization,
        "initials": user.initials,
    }


def _iso(value: datetime) -> str:
    return value.isoformat()


def _workspace_json(w: Workspace, *, full: bool) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": str(w.workspace_id),
        "name": w.name,
        "measure": w.measure.value,
        "status": w.status.value,
        "polygons": len(w.polygons),
        "area": " · ".join(p.name for p in w.polygons[:3]) or "Brusque, SC",
        "created_at": _iso(w.created_at),
        "updated_at": _iso(w.updated_at),
    }
    if full:
        data["features"] = [
            {
                "type": "Feature",
                "id": str(p.polygon_id),
                "properties": {"id": str(p.polygon_id), "code": p.code, "name": p.name},
                "geometry": {"type": "Polygon", "coordinates": [list(map(list, p.ring))]},
            }
            for p in w.polygons
        ]
    return data


def platform_router(
    auth: Authentication, workspaces: Workspaces, polygon_stats: GetPolygonStats, *, secure: bool
) -> APIRouter:
    router = APIRouter()

    def set_cookie(response: Response, token: str) -> None:
        response.set_cookie(
            COOKIE,
            token,
            max_age=SESSION_SECONDS,
            httponly=True,
            secure=secure,
            samesite="lax",
            path="/",
        )

    def current_user(request: Request) -> User:
        user = auth.current_user(request.cookies.get(COOKIE))
        if user is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sessão expirada. Entre de novo.")
        return user

    CurrentUser = Annotated[User, Depends(current_user)]  # noqa: N806 - alias de tipo

    # ------------------------------------------------------------------ autenticação

    @router.post("/auth/signup", status_code=201, tags=["conta"])
    def sign_up(body: SignUpBody, response: Response) -> dict[str, Any]:
        try:
            session = auth.sign_up(
                name=body.name,
                email=body.email,
                organization=body.organization,
                password=body.password,
            )
        except AuthError as error:
            raise HTTPException(400, str(error)) from error
        set_cookie(response, session.token)
        return {"user": _user_json(session.user)}

    @router.post("/auth/login", tags=["conta"])
    def log_in(body: LogInBody, response: Response) -> dict[str, Any]:
        try:
            session = auth.log_in(email=body.email, password=body.password)
        except AuthError as error:
            raise HTTPException(401, str(error)) from error
        set_cookie(response, session.token)
        return {"user": _user_json(session.user)}

    @router.post("/auth/logout", status_code=204, tags=["conta"])
    def log_out(request: Request, response: Response) -> None:
        token = request.cookies.get(COOKIE)
        if token:
            auth.log_out(token)
        response.delete_cookie(COOKIE, path="/")

    @router.get("/me", tags=["conta"])
    def me(user: CurrentUser) -> dict[str, Any]:
        return {"user": _user_json(user)}

    # ------------------------------------------------------------------ cenários

    def guard(fn: Any) -> Any:
        try:
            return fn()
        except WorkspaceNotFoundError as error:
            raise HTTPException(404, str(error)) from error
        except InvalidWorkspaceError as error:
            raise HTTPException(400, str(error)) from error

    @router.get("/workspaces", tags=["cenários do usuário"])
    def list_workspaces(user: CurrentUser) -> list[dict[str, Any]]:
        # inclui os polígonos: o painel desenha as miniaturas com as formas reais
        return [_workspace_json(w, full=True) for w in workspaces.list(user.user_id)]

    @router.post("/workspaces", status_code=201, tags=["cenários do usuário"])
    def create_workspace(body: WorkspaceBody, user: CurrentUser) -> dict[str, Any]:
        w = workspaces.create(user.user_id, name=body.name, measure=body.measure)
        return _workspace_json(w, full=True)

    @router.get("/workspaces/{workspace_id}", tags=["cenários do usuário"])
    def get_workspace(workspace_id: UUID, user: CurrentUser) -> dict[str, Any]:
        w = guard(lambda: workspaces.get(user.user_id, workspace_id))
        return _workspace_json(w, full=True)

    @router.patch("/workspaces/{workspace_id}", tags=["cenários do usuário"])
    def update_workspace(
        workspace_id: UUID, body: WorkspacePatch, user: CurrentUser
    ) -> dict[str, Any]:
        w = guard(
            lambda: workspaces.update(
                user.user_id,
                workspace_id,
                name=body.name,
                measure=body.measure,
                status=body.status,
            )
        )
        return _workspace_json(w, full=True)

    @router.delete("/workspaces/{workspace_id}", status_code=204, tags=["cenários do usuário"])
    def delete_workspace(workspace_id: UUID, user: CurrentUser) -> None:
        guard(lambda: workspaces.delete(user.user_id, workspace_id))

    @router.post(
        "/workspaces/{workspace_id}/polygons", status_code=201, tags=["cenários do usuário"]
    )
    def add_polygon(workspace_id: UUID, body: PolygonBody, user: CurrentUser) -> dict[str, Any]:
        polygon = guard(
            lambda: workspaces.add_polygon(
                user.user_id, workspace_id, name=body.name, ring=tuple(body.coordinates)
            )
        )
        return {"id": str(polygon.polygon_id), "code": polygon.code, "name": polygon.name}

    @router.delete(
        "/workspaces/{workspace_id}/polygons/{polygon_id}",
        status_code=204,
        tags=["cenários do usuário"],
    )
    def remove_polygon(workspace_id: UUID, polygon_id: UUID, user: CurrentUser) -> None:
        guard(lambda: workspaces.remove_polygon(user.user_id, workspace_id, polygon_id))

    # ------------------------------------------------------------------ camadas de um polígono

    @router.post("/syntax/polygon-stats", tags=["análise sintática"])
    def stats(body: StatsBody) -> dict[str, Any]:
        return dict(polygon_stats(list(body.coordinates)))

    return router
