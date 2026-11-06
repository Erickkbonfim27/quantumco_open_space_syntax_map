"""Rotas das camadas territoriais: perfil de um polígono e catálogo das fontes (públicas)."""

# sem `from __future__ import annotations`: o FastAPI resolve os tipos do corpo em tempo de execução

from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, Field

from quantumco.territory.application.queries import (
    GetPolygonProfile,
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
