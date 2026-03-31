"""Async HTTP client for the ShipRush REST API."""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx

from shiprush.models import (
    Address,
    Package,
    RateResult,
    ShipmentResult,
    TrackingResult,
    VoidResult,
)
from shiprush.xml_builder import (
    build_rate_request,
    build_ship_request,
    build_tracking_request,
    build_void_request,
)
from shiprush.xml_parser import (
    parse_rate_response,
    parse_ship_response,
    parse_track_response,
    parse_void_response,
)

if TYPE_CHECKING:
    from config import ShipRushConfig


class ShipRushClient:
    """Wraps ShipRush REST API endpoints with XML serialization.

    Accepts a config object so the token is resolved per-request via the
    config.shipping_token property (supports both env vars and AgentCore
    Identity vault).
    """

    def __init__(self, config: ShipRushConfig):
        self._config = config
        self._http = httpx.AsyncClient(timeout=30.0)

    async def close(self) -> None:
        await self._http.aclose()

    async def _get_headers(self) -> dict[str, str]:
        token = await self._config.get_shipping_token()
        return {
            "X-SHIPRUSH-SHIPPING-TOKEN": token,
            "Content-Type": "application/xml",
        }

    async def _post(self, path: str, body: str) -> str:
        url = f"{self._config.base_url}{path}"
        headers = await self._get_headers()
        response = await self._http.post(url, content=body, headers=headers)
        response.raise_for_status()
        return response.text

    async def get_rates(
        self,
        origin: Address,
        destination: Address,
        packages: list[Package],
        carrier_filter: str | None = None,
    ) -> list[RateResult]:
        xml = build_rate_request(origin, destination, packages, carrier_filter)
        response_xml = await self._post("/shipmentservice.svc/shipment/rateshopping", xml)
        return parse_rate_response(response_xml)

    async def create_shipment(
        self,
        origin: Address,
        destination: Address,
        packages: list[Package],
        quote_id: str,
        reference: str | None = None,
        carrier: str | None = None,
        service_code: str | None = None,
        shipping_account_id: str | None = None,
    ) -> ShipmentResult:
        xml = build_ship_request(origin, destination, packages, quote_id, reference, carrier, service_code, shipping_account_id)
        response_xml = await self._post("/shipmentservice.svc/shipment/ship", xml)
        return parse_ship_response(response_xml)

    async def track_shipment(self, shipment_id: str) -> TrackingResult:
        xml = build_tracking_request(shipment_id)
        response_xml = await self._post("/shipmentservice.svc/shipment/tracking", xml)
        return parse_track_response(response_xml)

    async def void_shipment(self, shipment_id: str) -> VoidResult:
        xml = build_void_request(shipment_id)
        response_xml = await self._post("/shipmentservice.svc/shipment/void", xml)
        return parse_void_response(response_xml)
