"""Rotas das camadas territoriais: perfil de um polígono e catálogo das fontes (públicas)."""

# sem `from __future__ import annotations`: o FastAPI resolve os tipos do corpo em tempo de execução

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

from quantumco.territory.application.queries import GetPolygonProfile, UnknownLayerError

Coordinates = Annotated[list[tuple[float, float]], Field(min_length=3, max_length=500)]


class ProfileBody(BaseModel):
    coordinates: Coordinates


def territory_router(profile: GetPolygonProfile) -> APIRouter:
    router = APIRouter(tags=["camadas territoriais"])

    @router.get("/territory/layers")
    def layers() -> list[dict[str, Any]]:
        return [dict(layer) for layer in profile.layers()]

    @router.get("/territory/map/{name}")
    def map_layer(name: str) -> Response:
        try:
            data = profile.map_layer(name)
        except UnknownLayerError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        if data is None:
            raise HTTPException(status_code=503, detail="camada ainda não importada")
        return Response(
            content=data,
            media_type="application/geo+json",
            headers={"Cache-Control": "public, max-age=3600"},
        )

    @router.post("/territory/polygon-profile")
    def polygon_profile(body: ProfileBody) -> dict[str, Any]:
        result = profile(list(body.coordinates))
        if result is None:
            raise HTTPException(
                status_code=503,
                detail="camadas territoriais não importadas; rode `quantumco territory import`",
            )
        return {**result, "layers": [dict(layer) for layer in profile.layers()]}

    return router
