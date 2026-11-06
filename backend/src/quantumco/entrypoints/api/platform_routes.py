"""Rotas da Plataforma: conta e perfil, cenários do usuário (polígonos, edições da rede e fila
de cálculo) e estatísticas de polígonos."""

# sem `from __future__ import annotations`: o FastAPI precisa resolver CurrentUser (local)

import logging
import re
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated, Any, Literal, TypeVar
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from quantumco.bootstrap.platform import Platform
from quantumco.identity.application.account import (
    AlreadyVerifiedError,
    InvalidLinkError,
    TooSoonError,
)
from quantumco.identity.application.auth import AuthError
from quantumco.identity.application.ports import (
    AvatarStorageUnavailableError,
    MailDeliveryError,
)
from quantumco.identity.application.profile import ProfileError, WrongPasswordError
from quantumco.identity.domain.avatar import MAX_BYTES as AVATAR_MAX_BYTES
from quantumco.identity.domain.user import User
from quantumco.scenarios.application.ports import QueueUnavailableError
from quantumco.scenarios.application.runs import RunView, result_name
from quantumco.scenarios.application.workspaces import WorkspaceNotFoundError
from quantumco.scenarios.domain.network_edits import NetworkEdit
from quantumco.scenarios.domain.run import RunRefusedError
from quantumco.scenarios.domain.workspace import (
    InvalidWorkspaceError,
    Measure,
    Status,
    Workspace,
)
from quantumco.syntax_analysis.application.queries import GetScenario

log = logging.getLogger(__name__)

COOKIE = "qc_session"
SESSION_SECONDS = 30 * 24 * 3600
GEOJSON = "application/geo+json"

Coordinates = Annotated[list[tuple[float, float]], Field(min_length=3, max_length=500)]
Line = Annotated[list[tuple[float, float]], Field(min_length=2, max_length=500)]
T = TypeVar("T")


class SignUpBody(BaseModel):
    name: str = Field(max_length=200)
    email: str = Field(max_length=254)
    organization: str | None = Field(default=None, max_length=200)
    password: str = Field(max_length=256)


class LogInBody(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=256)


class ProfilePatch(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    organization: str | None = Field(default=None, max_length=200)
    preferences: dict[str, str] | None = None


class EmailBody(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=256)


class TokenBody(BaseModel):
    token: str = Field(min_length=10, max_length=200)


class ForgotBody(BaseModel):
    email: str = Field(max_length=254)


class ResetBody(BaseModel):
    token: str = Field(min_length=10, max_length=200)
    new_password: str = Field(max_length=256)


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


class EditBody(BaseModel):
    type: Literal["remove", "close", "add", "reroute"]
    link_id: str | None = Field(default=None, max_length=64)
    coords: Line | None = None
    label: str | None = Field(default=None, max_length=120)


class EditsBody(BaseModel):
    edits: list[EditBody] = Field(max_length=200)


class StatsBody(BaseModel):
    coordinates: Coordinates


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _user_json(user: User) -> dict[str, Any]:
    avatar = None
    if user.avatar_updated_at:  # versão na URL: a foto nova não fica presa no cache
        avatar = f"/api/v1/me/avatar?v={int(user.avatar_updated_at.timestamp())}"
    return {
        "id": str(user.user_id),
        "name": user.name,
        "email": str(user.email),
        "organization": user.organization,
        "initials": user.initials,
        "avatar_url": avatar,
        "preferences": dict(user.preferences),
        "created_at": _iso(user.created_at),
        "email_verified": user.email_verified,
        "pending_email": str(user.pending_email) if user.pending_email else None,
    }


# Em desenvolvimento, os links dos e-mails apontam para o front local que fez o pedido.
_LOCAL_ORIGIN = re.compile(r"^http://(localhost|127\.0\.0\.1)(:\d{1,5})?$")


def link_base(request: Request, public_base_url: str) -> str:
    """Base dos links: QC_PUBLIC_BASE_URL, ou a origem local (só localhost) em dev."""
    origin = request.headers.get("origin") or ""
    if not origin:
        referer = request.headers.get("referer") or ""
        match = re.match(r"^(https?://[^/]+)", referer)
        origin = match.group(1) if match else ""
    if _LOCAL_ORIGIN.match(origin):
        return origin
    return public_base_url.rstrip("/")


def _workspace_json(w: Workspace, *, full: bool) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": str(w.workspace_id),
        "name": w.name,
        "measure": w.measure.value,
        "status": w.status.value,
        "polygons": len(w.polygons),
        "edits_count": len(w.edits),
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
        data["edits"] = [e.to_json() for e in w.edits]
    return data


def _run_json(view: RunView) -> dict[str, Any]:
    run = view.run
    return {
        "id": str(run.run_id),
        "status": run.status.value,
        "stage": run.stage,
        "stages": run.stages,
        "edits": len(run.edits),
        "edit_list": [e.to_json() for e in run.edits],  # a tela compara com as edições atuais
        "created_at": _iso(run.created_at),
        "started_at": _iso(run.started_at),
        "finished_at": _iso(run.finished_at),
        "attempts": run.attempts,
        "error": run.error,
        "result": run.result,
        "queue": {"position": view.position, "running": view.running, "workers": view.workers},
        "expected_engine_seconds": view.expected_engine_s,
        # relógio do servidor: a tela calcula o tempo decorrido sem depender do relógio local
        "server_time": datetime.now(UTC).isoformat(),
    }


def platform_router(
    platform: Platform, results: GetScenario, *, secure: bool, owner_email: str = ""
) -> APIRouter:
    router = APIRouter()
    auth = platform.auth

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

    _auth_routes(router, platform, set_cookie)
    _profile_routes(router, platform, current_user)
    _workspace_routes(router, platform, results, current_user, owner_email)
    return router


def _account_guard[R](fn: Callable[[], R]) -> R:
    """Erros da conta → HTTP com a mensagem pronta para a tela."""
    try:
        return fn()
    except WrongPasswordError as error:
        raise HTTPException(403, str(error)) from error
    except TooSoonError as error:
        raise HTTPException(429, str(error)) from error
    except AlreadyVerifiedError as error:
        raise HTTPException(409, str(error)) from error
    except (InvalidLinkError, ProfileError) as error:
        raise HTTPException(400, str(error)) from error
    except AvatarStorageUnavailableError as error:
        raise HTTPException(
            503, "O armazenamento de fotos está indisponível agora. Tente mais tarde."
        ) from error
    except MailDeliveryError as error:
        raise HTTPException(
            502, "Não foi possível enviar o e-mail agora. Tente de novo em alguns minutos."
        ) from error


def _auth_routes(
    router: APIRouter, platform: Platform, set_cookie: Callable[[Response, str], None]
) -> None:
    auth, account = platform.auth, platform.account

    # ------------------------------------------------------------------ autenticação

    @router.post("/auth/signup", status_code=201, tags=["conta"])
    def sign_up(body: SignUpBody, request: Request, response: Response) -> dict[str, Any]:
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
        try:  # o cadastro vale mesmo se o e-mail de confirmação falhar (dá para reenviar)
            account.send_verification(session.user, link_base(request, platform.public_base_url))
        except Exception:
            log.warning("e-mail de confirmação do cadastro não enviado", exc_info=True)
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

    @router.post("/auth/confirm-email", tags=["conta"])
    def confirm_email(body: TokenBody) -> dict[str, Any]:
        user, purpose = _account_guard(lambda: account.confirm(body.token))
        return {"user": _user_json(user), "purpose": purpose.value}

    @router.post("/auth/password/forgot", status_code=202, tags=["conta"])
    def forgot_password(body: ForgotBody, request: Request) -> dict[str, Any]:
        base = link_base(request, platform.public_base_url)
        _account_guard(lambda: account.forgot_password(body.email, base))
        return {"sent": True}  # igual exista ou não a conta

    @router.post("/auth/password/reset", tags=["conta"])
    def reset_password(body: ResetBody, request: Request, response: Response) -> dict[str, Any]:
        base = link_base(request, platform.public_base_url)
        session = _account_guard(
            lambda: account.reset_password(body.token, body.new_password, base)
        )
        set_cookie(response, session.token)
        return {"user": _user_json(session.user)}


def _profile_routes(
    router: APIRouter, platform: Platform, current_user: Callable[[Request], User]
) -> None:
    auth, profile, account = platform.auth, platform.profile, platform.account
    CurrentUser = Annotated[User, Depends(current_user)]  # noqa: N806 - alias de tipo

    def fresh(request: Request, fallback: User) -> User:
        return auth.current_user(request.cookies.get(COOKIE)) or fallback

    # ------------------------------------------------------------------ perfil

    @router.get("/me", tags=["conta"])
    def me(user: CurrentUser) -> dict[str, Any]:
        return {"user": _user_json(user)}

    @router.patch("/me", tags=["conta"])
    def update_me(body: ProfilePatch, user: CurrentUser) -> dict[str, Any]:
        sent = body.model_fields_set
        organization = (body.organization or "").strip()
        updated = _account_guard(
            lambda: profile.update(
                user,
                name=body.name,
                organization=organization or None,
                clear_organization="organization" in sent and not organization,
                preferences=body.preferences,
            )
        )
        return {"user": _user_json(updated)}

    @router.post("/me/verification", status_code=202, tags=["conta"])
    def resend_verification(request: Request, user: CurrentUser) -> dict[str, Any]:
        base = link_base(request, platform.public_base_url)
        sent_to = _account_guard(lambda: account.send_verification(user, base))
        return {"sent_to": str(sent_to)}

    @router.post("/me/email", status_code=202, tags=["conta"])
    def change_email(body: EmailBody, request: Request, user: CurrentUser) -> dict[str, Any]:
        base = link_base(request, platform.public_base_url)
        updated, sent_to = _account_guard(
            lambda: account.request_email_change(
                user, email=body.email, password=body.password, base_url=base
            )
        )
        return {"user": _user_json(updated), "sent_to": str(sent_to)}

    @router.delete("/me/email/pending", tags=["conta"])
    def cancel_email_change(user: CurrentUser) -> dict[str, Any]:
        return {"user": _user_json(account.cancel_email_change(user))}

    @router.post("/me/password", status_code=202, tags=["conta"])
    def request_password_change(request: Request, user: CurrentUser) -> dict[str, Any]:
        base = link_base(request, platform.public_base_url)
        sent_to = _account_guard(lambda: account.request_password_change(user, base))
        return {"sent_to": str(sent_to)}

    @router.put("/me/avatar", tags=["conta"])
    async def put_avatar(request: Request, user: CurrentUser) -> dict[str, Any]:
        declared = int(request.headers.get("content-length") or 0)
        if declared > AVATAR_MAX_BYTES:
            raise HTTPException(413, "A foto pode ter no máximo 512 KB.")
        content = await request.body()
        _account_guard(lambda: profile.set_avatar(user, content[: AVATAR_MAX_BYTES + 1]))
        return {"user": _user_json(fresh(request, user))}

    @router.delete("/me/avatar", tags=["conta"])
    def delete_avatar(request: Request, user: CurrentUser) -> dict[str, Any]:
        _account_guard(lambda: profile.remove_avatar(user))
        return {"user": _user_json(fresh(request, user))}

    @router.get("/me/avatar", tags=["conta"], response_class=Response)
    def get_avatar(user: CurrentUser) -> Response:
        avatar = _account_guard(lambda: profile.avatar(user))
        if avatar is None:
            raise HTTPException(404, "Sem foto de perfil.")
        return Response(
            content=avatar.content,
            media_type=avatar.media_type,
            headers={
                "Cache-Control": "private, max-age=31536000, immutable",
                "X-Content-Type-Options": "nosniff",
            },
        )


def _workspace_routes(
    router: APIRouter,
    platform: Platform,
    results: GetScenario,
    current_user: Callable[[Request], User],
    owner_email: str,
) -> None:
    workspaces, runs = platform.workspaces, platform.runs
    owner = owner_email.strip().lower()
    CurrentUser = Annotated[User, Depends(current_user)]  # noqa: N806 - alias de tipo

    # ------------------------------------------------------------------ cenários

    def guard(fn: Callable[[], T]) -> T:
        try:
            return fn()
        except WorkspaceNotFoundError as error:
            raise HTTPException(404, str(error)) from error
        except InvalidWorkspaceError as error:
            raise HTTPException(400, str(error)) from error
        except RunRefusedError as error:
            raise HTTPException(409, str(error)) from error
        except QueueUnavailableError as error:
            raise HTTPException(
                503, "A fila de cálculo está fora do ar. Tente de novo em instantes."
            ) from error

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
        platform.forget_result(result_name(workspace_id))

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

    # ------------------------------------------------------------------ edições da rede e fila

    @router.put("/workspaces/{workspace_id}/edits", tags=["cenários do usuário"])
    def put_edits(workspace_id: UUID, body: EditsBody, user: CurrentUser) -> dict[str, Any]:
        def apply() -> Workspace:
            edits = [NetworkEdit.from_json(e.model_dump(exclude_none=True)) for e in body.edits]
            return workspaces.set_edits(user.user_id, workspace_id, edits)

        return _workspace_json(guard(apply), full=True)

    @router.post("/workspaces/{workspace_id}/runs", status_code=202, tags=["cenários do usuário"])
    def request_run(workspace_id: UUID, user: CurrentUser) -> dict[str, Any]:
        unlimited = bool(owner) and str(user.email) == owner
        view = guard(lambda: runs.request(user.user_id, workspace_id, unlimited=unlimited))
        return _run_json(view)

    # antes de /runs/{run_id}: "latest" não é UUID
    @router.get("/workspaces/{workspace_id}/runs/latest", tags=["cenários do usuário"])
    def latest_run(workspace_id: UUID, user: CurrentUser) -> dict[str, Any] | None:
        view = guard(lambda: runs.latest(user.user_id, workspace_id))
        return _run_json(view) if view else None

    @router.get("/workspaces/{workspace_id}/runs/{run_id}", tags=["cenários do usuário"])
    def get_run(workspace_id: UUID, run_id: UUID, user: CurrentUser) -> dict[str, Any]:
        return _run_json(guard(lambda: runs.view(user.user_id, workspace_id, run_id)))

    @router.delete("/workspaces/{workspace_id}/runs/{run_id}", tags=["cenários do usuário"])
    def cancel_run(workspace_id: UUID, run_id: UUID, user: CurrentUser) -> dict[str, Any]:
        return _run_json(guard(lambda: runs.cancel(user.user_id, workspace_id, run_id)))

    @router.get("/workspaces/{workspace_id}/result/manifest", tags=["cenários do usuário"])
    def result_manifest(workspace_id: UUID, user: CurrentUser) -> dict[str, Any]:
        guard(lambda: workspaces.get(user.user_id, workspace_id))
        return dict(results(result_name(workspace_id)).manifest)

    @router.get(
        "/workspaces/{workspace_id}/result/links",
        tags=["cenários do usuário"],
        response_class=Response,
    )
    def result_links(workspace_id: UUID, user: CurrentUser) -> Response:
        guard(lambda: workspaces.get(user.user_id, workspace_id))
        body = results(result_name(workspace_id)).links_geojson
        return Response(content=body, media_type=GEOJSON, headers={"Cache-Control": "no-store"})

    # ------------------------------------------------------------------ camadas de um polígono

    @router.post("/syntax/polygon-stats", tags=["análise sintática"])
    def stats(body: StatsBody) -> dict[str, Any]:
        return dict(platform.polygon_stats(list(body.coordinates)))
