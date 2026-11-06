"""Rotas das camadas territoriais: perfil de um polígono e catálogo das fontes (públicas)."""

# sem `from __future__ import annotations`: o FastAPI resolve os tipos do corpo em tempo de execução

from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, Field

from quantumco.territory.application.queries import (
    GetPolygonProfile,
    InvalidTileError,
    SearchAddresses,
    UnknownLayerError,
)

Coordinates = Annotated[list[tuple[float, float]], Field(min_length=3, max_length=500)]


class ProfileBody(BaseModel):
    coordinates: Coordinates


def territory_router(
    profile: GetPolygonProfile, addresses: Callable[[], SearchAddresses]
) -> APIRouter:
    router = APIRouter(tags=["camadas territoriais"])

    @router.get("/territory/addresses")
    def search_addresses(
        response: Response, q: Annotated[str, Query(max_length=120)] = ""
    ) -> list[dict[str, Any]]:
        """Busca de endereços em Brusque (CNEFE 2022): "rua hercilio luz 120", "av beira rio"."""
        response.headers["Cache-Control"] = "public, max-age=300"
        return [
            {
                "label": hit.label,
                "street": hit.street,
                "number": hit.number,
                "locality": hit.locality,
                "cep": hit.cep,
                "lon": round(hit.lon, 6),
                "lat": round(hit.lat, 6),
                "units": hit.units,
                "exact": hit.exact,
            }
            for hit in addresses()(q)
        ]

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

    @router.get("/territory/images")
    def images() -> list[dict[str, Any]]:
        """Camadas da grade de 30 m prontas para o mapa (fonte `image` do MapLibre)."""
        return [
            {**dict(img), "url": f"territory/images/{img['layer']}.png"} for img in profile.images()
        ]

    @router.get("/territory/images/{layer}.png")
    def image(layer: str) -> Response:
        try:
            png = profile.image(layer)
        except UnknownLayerError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        if png is None:
            raise HTTPException(status_code=404, detail="imagem não importada")
        return Response(
            content=png, media_type="image/png", headers={"Cache-Control": "public, max-age=3600"}
        )

    @router.get("/territory/tiles/buildings/{z}/{x}/{y}.mvt")
    def building_tile(z: int, x: int, y: int) -> Response:
        try:
            tile = profile.building_tile(z, x, y)
        except InvalidTileError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return Response(
            content=tile,
            media_type="application/vnd.mapbox-vector-tile",
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
