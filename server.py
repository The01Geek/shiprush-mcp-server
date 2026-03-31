"""ShipRush MCP Server — exposes shipping tools over the Model Context Protocol.

Supports three deployment modes (controlled by environment variables):

  1. Local dev:       No special env vars. Runs mcp.run() on localhost.
  2. AgentCore Runtime: DOCKER_CONTAINER=1. Adds AgentCoreIdentityMiddleware
                       to extract WorkloadAccessToken for vault-based token
                       resolution.
  3. Standalone:      DOCKER_CONTAINER=1 + STANDALONE=1. Adds ApiKeyMiddleware
                       for Gateway-to-server auth. ShipRush token via env var.
"""

import logging
import os

from mcp.server.fastmcp import FastMCP
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from config import config
from shiprush.client import ShipRushClient
from shiprush.models import Address, Package
from shiprush.xml_parser import ShipRushApiError

log = logging.getLogger(__name__)


class AgentCoreIdentityMiddleware:
    """Extract WorkloadAccessToken header from AgentCore Runtime requests.

    AgentCore Runtime injects this header on every invocation. FastMCP's
    Starlette app doesn't read it, so this middleware bridges the gap by
    storing it in BedrockAgentCoreContext for the @requires_api_key decorator.
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            headers = dict(scope.get("headers", []))
            # ASGI headers are lowercase bytes
            token = headers.get(b"workloadaccesstoken")
            if not token:
                # Log all headers to diagnose which header name Runtime uses
                header_names = [k.decode("utf-8", errors="replace") for k, _ in scope.get("headers", [])]
                log.warning("No workloadaccesstoken header. Available headers: %s", header_names)
                # Try alternative header names
                for key in (b"workload-access-token", b"x-workload-access-token", b"workload_access_token"):
                    token = headers.get(key)
                    if token:
                        log.info("Found workload token in header: %s", key)
                        break
            if token:
                try:
                    from bedrock_agentcore.runtime.context import BedrockAgentCoreContext
                    BedrockAgentCoreContext.set_workload_access_token(token.decode("utf-8"))
                    log.info("Set workload access token from request header")
                except ImportError:
                    log.warning("bedrock_agentcore.runtime.context not available")
        await self.app(scope, receive, send)


class ApiKeyMiddleware:
    """Validate X-API-Key header for standalone deployments behind AgentCore Gateway.

    When MCP_API_KEY is set, every request must include a matching
    X-API-Key header. This secures the standalone server so only the
    Gateway (which injects the key via its credential provider) can call it.
    """

    def __init__(self, app: ASGIApp):
        self.app = app
        self._api_key = os.environ.get("MCP_API_KEY")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and self._api_key:
            headers = dict(scope.get("headers", []))
            provided = headers.get(b"x-api-key")
            if not provided or provided.decode("utf-8") != self._api_key:
                response = PlainTextResponse("Unauthorized", status_code=401)
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


# Binds to 0.0.0.0 for container deployment (AgentCore Runtime).
# Stateless mode — no session persistence, simplest AgentCore path.
mcp = FastMCP(
    name="shiprush-mcp-server",
    host="0.0.0.0",
    stateless_http=True,
)

client = ShipRushClient(config=config)


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
    if os.environ.get("DOCKER_CONTAINER"):
        import uvicorn

        app = mcp.streamable_http_app()

        if os.environ.get("STANDALONE"):
            # Standalone mode: behind AgentCore Gateway, validate API key.
            app.add_middleware(ApiKeyMiddleware)
            log.info("Starting in STANDALONE mode (API key auth)")
        else:
            # AgentCore Runtime mode: extract WorkloadAccessToken for vault.
            app.add_middleware(AgentCoreIdentityMiddleware)
            log.info("Starting in AgentCore Runtime mode (vault auth)")

        uvicorn.run(app, host="0.0.0.0", port=8000)
    else:
        mcp.run(transport="streamable-http")
