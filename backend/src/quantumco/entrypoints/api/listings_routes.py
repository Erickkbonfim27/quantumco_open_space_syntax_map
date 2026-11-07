"""Imóveis à venda da cidade para o mapa (prova de conceito, docs/adr/0003).

Só com login e com a flag `listings_glue_api` ligada: os dados não são redistribuídos.
"""

# sem `from __future__ import annotations`: o FastAPI resolve os tipos em tempo de execução

from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from quantumco.identity.domain.user import User
from quantumco.listings.application.ports import FeatureDisabledError
from quantumco.listings.application.queries import ListingsForMap


def listings_router(
    query: Callable[[], ListingsForMap],
    city_of: Callable[..., str],
    current_user: Callable[[Request], User],
) -> APIRouter:
    """`query` é preguiçosa: o pool do banco só abre no primeiro pedido."""
    router = APIRouter(tags=["imóveis à venda"])
    City = Annotated[str, Depends(city_of)]  # noqa: N806 - alias de tipo
    CurrentUser = Annotated[User, Depends(current_user)]  # noqa: N806 - alias de tipo

    @router.get("/listings")
    def listings(response: Response, city: City, _user: CurrentUser) -> dict[str, Any]:
        """Anúncios ativos com ponto (GeoJSON): tipo, área, cômodos, valores, foto e link."""
        try:
            collection = query()(city)
        except FeatureDisabledError as exc:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                "Camada de imóveis desligada (flag listings_glue_api).",
            ) from exc
        response.headers["Cache-Control"] = "private, max-age=60"
        return collection

    return router
