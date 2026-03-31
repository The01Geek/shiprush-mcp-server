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
    build_void_request,
)
from shiprush.xml_parser import (
    parse_rate_response,
    parse_ship_response,
    parse_track_response,
    parse_void_response,
)


class ShipRushClient:
    def __init__(self, token: str, base_url: str):
        self._token = token
        self._base_url = base_url
        self._http = httpx.AsyncClient(timeout=30.0)

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "X-SHIPRUSH-SHIPPING-TOKEN": self._token,
            "Content-Type": "application/xml",
        }

    async def _post(self, path: str, body: str) -> str:
        url = f"{self._base_url}{path}"
        response = await self._http.post(url, content=body, headers=self._headers)
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
        response_xml = await self._post("/shipmentservice.svc/shipment/rate", xml)
        return parse_rate_response(response_xml)

    async def create_shipment(
        self,
        origin: Address,
        destination: Address,
        packages: list[Package],
        carrier: str,
        service_name: str,
        reference: str | None = None,
    ) -> ShipmentResult:
        xml = build_ship_request(origin, destination, packages, carrier, service_name, reference)
        response_xml = await self._post("/shipmentservice.svc/shipment/ship", xml)
        return parse_ship_response(response_xml)

    async def track_shipment(
        self,
        tracking_number: str,
        carrier: str | None = None,
    ) -> TrackingResult:
        from shiprush.xml_builder import build_tracking_request
        xml = build_tracking_request(tracking_number)
        response_xml = await self._post("/shipmentservice.svc/shipment/tracking", xml)
        return parse_track_response(response_xml)

    async def void_shipment(
        self,
        tracking_number: str,
        carrier: str | None = None,
    ) -> VoidResult:
        xml = build_void_request(tracking_number, carrier)
        response_xml = await self._post("/shipmentservice.svc/shipment/void", xml)
        return parse_void_response(response_xml)

