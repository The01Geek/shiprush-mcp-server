"""ShipRush MCP Server — exposes shipping tools over the Model Context Protocol."""

import logging

from mcp.server.fastmcp import FastMCP

from config import config
from shiprush.client import ShipRushClient
from shiprush.models import Address, Package
from shiprush.xml_parser import ShipRushApiError

log = logging.getLogger(__name__)

# Binds to 0.0.0.0 for container deployment (AgentCore Runtime).
# Stateless mode — no session persistence, simplest AgentCore path.
mcp = FastMCP(
    name="shiprush-mcp-server",
    host="0.0.0.0",
    stateless_http=True,
)

client = ShipRushClient(token=config.shipping_token, base_url=config.base_url)


@mcp.tool()
async def get_shipping_rates(
    origin_name: str | None = None,
    origin_company: str | None = None,
    origin_street1: str = "",
    origin_street2: str | None = None,
    origin_city: str = "",
    origin_state: str = "",
    origin_postal_code: str = "",
    origin_country: str = "US",
    destination_name: str | None = None,
    destination_company: str | None = None,
    destination_street1: str = "",
    destination_street2: str | None = None,
    destination_city: str = "",
    destination_state: str = "",
    destination_postal_code: str = "",
    destination_country: str = "US",
    package_weight_lb: float = 1.0,
    package_length_in: float | None = None,
    package_width_in: float | None = None,
    package_height_in: float | None = None,
    carrier_filter: str | None = None,
) -> dict:
    """Get shipping rate quotes across carriers (FedEx, UPS, USPS). Returns available services with prices and estimated delivery dates. Use this before create_shipment to find the best rate."""
    origin = Address(name=origin_name, company=origin_company, street1=origin_street1, street2=origin_street2, city=origin_city, state=origin_state, postal_code=origin_postal_code, country=origin_country)
    destination = Address(name=destination_name, company=destination_company, street1=destination_street1, street2=destination_street2, city=destination_city, state=destination_state, postal_code=destination_postal_code, country=destination_country)
    packages = [Package(weight_lb=package_weight_lb, length_in=package_length_in, width_in=package_width_in, height_in=package_height_in)]
    try:
        rates = await client.get_rates(origin, destination, packages, carrier_filter)
        return {"rates": [r.model_dump() for r in rates]}
    except (ShipRushApiError, Exception) as e:
        log.exception("get_shipping_rates failed")
        return {"error": str(e), "code": "RATE_ERROR"}


@mcp.tool()
async def create_shipment(
    quote_id: str,
    origin_name: str | None = None,
    origin_company: str | None = None,
    origin_street1: str = "",
    origin_street2: str | None = None,
    origin_city: str = "",
    origin_state: str = "",
    origin_postal_code: str = "",
    origin_country: str = "US",
    destination_name: str | None = None,
    destination_company: str | None = None,
    destination_street1: str = "",
    destination_street2: str | None = None,
    destination_city: str = "",
    destination_state: str = "",
    destination_postal_code: str = "",
    destination_country: str = "US",
    package_weight_lb: float = 1.0,
    package_length_in: float | None = None,
    package_width_in: float | None = None,
    package_height_in: float | None = None,
    carrier: str | None = None,
    service_code: str | None = None,
    shipping_account_id: str | None = None,
    reference: str | None = None,
) -> dict:
    """Create a shipment and generate a shipping label. Call get_shipping_rates first, then pass quote_id, carrier, service_code, and shipping_account_id from the chosen rate. Returns shipment_id, tracking number, label URL, and cost."""
    origin = Address(name=origin_name, company=origin_company, street1=origin_street1, street2=origin_street2, city=origin_city, state=origin_state, postal_code=origin_postal_code, country=origin_country)
    destination = Address(name=destination_name, company=destination_company, street1=destination_street1, street2=destination_street2, city=destination_city, state=destination_state, postal_code=destination_postal_code, country=destination_country)
    packages = [Package(weight_lb=package_weight_lb, length_in=package_length_in, width_in=package_width_in, height_in=package_height_in)]
    try:
        result = await client.create_shipment(origin, destination, packages, quote_id, reference, carrier, service_code, shipping_account_id)
        return result.model_dump()
    except (ShipRushApiError, Exception) as e:
        log.exception("create_shipment failed")
        return {"error": str(e), "code": "SHIP_ERROR"}


@mcp.tool()
async def track_shipment(
    shipment_id: str,
) -> dict:
    """Get tracking status and scan history for a shipment. Use the shipment_id returned by create_shipment."""
    try:
        result = await client.track_shipment(shipment_id)
        return result.model_dump()
    except (ShipRushApiError, Exception) as e:
        log.exception("track_shipment failed")
        return {"error": str(e), "code": "TRACK_ERROR"}


@mcp.tool()
async def void_shipment(
    shipment_id: str,
) -> dict:
    """Cancel/void a shipping label. Use the shipment_id returned by create_shipment."""
    try:
        result = await client.void_shipment(shipment_id)
        return result.model_dump()
    except (ShipRushApiError, Exception) as e:
        log.exception("void_shipment failed")
        return {"error": str(e), "code": "VOID_ERROR"}


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
