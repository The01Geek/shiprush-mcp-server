# ShipRush MCP Server — Design Document

**Date:** 2026-03-30 (updated 2026-03-31)
**Status:** Implemented and verified
**Approach:** Python FastMCP on AWS AgentCore Runtime
**Repo:** https://github.com/The01Geek/shiprush-mcp-server

---

## 1. Overview

A reusable MCP server that wraps the ShipRush shipping REST API, exposing multi-carrier shipping operations as MCP tools. The server deploys to AWS Bedrock AgentCore Runtime as a stateless ARM64 container, enabling AI agents (Strands, Claude Code, Q CLI) to automate shipping workflows.

### Goals

- Expose core ShipRush operations as MCP tools: rate shopping, ship, track, void
- Deploy natively on AgentCore Runtime via the starter toolkit (2-command deploy)
- Target internal workflow automation first, with a path to broader distribution via AgentCore Gateway
- Support ShipRush sandbox and production environments via configuration

### Non-Goals (v1)

- Multi-tenant per-request token routing (one ShipRush account per deployment)
- AgentCore Gateway registration and OAuth (future)
- Order management / store integration
- Stateful interactions (elicitation, sampling, progress notifications)
- UI widgets / MCP app resources

---

## 2. Architecture

```
+-----------------------------------------------------+
|  AWS AgentCore Runtime                              |
|                                                     |
|  +-----------------------------------------------+  |
|  |  ShipRush MCP Server (ARM64 Container)        |  |
|  |  FastMCP - Python 3.11+ - Stateless HTTP      |  |
|  |  0.0.0.0:8000/mcp                             |  |
|  |                                               |  |
|  |  Tools:                                       |  |
|  |  +-- get_shipping_rates (rate shopping)       |  |
|  |  +-- create_shipment   (ship via quote)       |  |
|  |  +-- track_shipment    (by shipment_id)       |  |
|  |  +-- void_shipment     (by shipment_id)       |  |
|  |                                               |  |
|  |  ShipRush Client Layer (httpx async)           |  |
|  |  -> HTTPS -> ShipRush REST API (XML)          |  |
|  |     Headers: X-SHIPRUSH-SHIPPING-TOKEN        |  |
|  +-----------------------------------------------+  |
|                                                     |
+------------------+----------------------------------+
                   | Streamable HTTP (JSON-RPC)
                   |
           +-------+--------+
           |  MCP Clients   |
           |  - Strands Agent|
           |  - Claude Code  |
           |  - Q CLI        |
           +----------------+
```

### Key Decisions

- **Stateless mode** (`stateless_http=True`) — no session persistence, simplest AgentCore path
- **ShipRush tokens as environment variables** — one account per deployment instance
- **Thin client wrapper** — `httpx` for async HTTP to ShipRush endpoints
- **XML handled internally** — ShipRush API uses XML TShipment blocks; the MCP surface is clean JSON
- **No `$ref` in schemas** — AgentCore requires fully resolved, self-contained JSON schemas
- **Flat tool parameters** — all primitives, no nested Pydantic objects, to avoid `$ref` in generated schemas

### AgentCore Compliance

| Requirement | Implementation |
|---|---|
| Transport | Streamable HTTP |
| Host/Port | 0.0.0.0:8000 |
| Container arch | ARM64 |
| Protocol versions | 2025-06-18, 2025-03-26 |
| Session handling | Accept platform-provided Mcp-Session-Id |
| Tool schemas | Fully resolved, no $ref/$defs |
| RPC format | JSON-RPC |

---

## 3. Tool Definitions

### 3.1 `get_shipping_rates`

Rate-shop across all carriers configured in the ShipRush account.

**Endpoint:** `POST /shipmentservice.svc/shipment/rateshopping`

**Input:** Origin/destination addresses (flat params), package weight/dimensions, optional `carrier_filter`

**Output:**
```json
{
  "rates": [
    {
      "carrier": "17",
      "service_name": "USPS Ground Advantage",
      "service_code": "USPSGNDADV",
      "rate_amount": 9.46,
      "currency": "USD",
      "estimated_delivery_date": "4/4/2026 12:00:00 AM",
      "transit_days": 4,
      "quote_id": "rate_abc123",
      "shipping_account_id": "049082f7-..."
    }
  ]
}
```

**Design note:** Uses `/shipment/rateshopping` (not `/shipment/rate`) to return rates across all configured carriers in one call. The carrier code is auto-detected from the service code pattern since the rate shopping response doesn't include a carrier type field.

### 3.2 `create_shipment`

Create a shipment and generate a label using a quote from rate shopping.

**Endpoint:** `POST /shipmentservice.svc/shipment/ship`

**Input:** `quote_id` (required), `carrier`, `service_code`, `shipping_account_id` (from rate response), origin/destination addresses, package details, optional `reference`

**Output:**
```json
{
  "shipment_id": "c05d8af6-...",
  "tracking_number": "9434636208235322685476",
  "carrier": "17",
  "service_name": "USPSGNDADV",
  "total_cost": 9.46,
  "currency": "USD"
}
```

**Design notes:**
- Uses `ShipViaQuoteId=true` with `ShipmentQuoteId` from rate shopping to ensure shipped rate matches quoted rate
- `Carrier` element is required even when using quote — API won't resolve it from the quote alone
- Tracking number is returned in `ShipmentNumber` (not `TrackingNumber`) — parser handles both fields
- `shipment_id` is critical — it's the only way to track or void this shipment later

### 3.3 `track_shipment`

Get tracking status and scan history.

**Endpoint:** `POST /shipmentservice.svc/shipment/tracking`

**Input:** `shipment_id` (ShipRush internal UUID from `create_shipment`)

**Output:**
```json
{
  "shipment_id": "c05d8af6-...",
  "tracking_number": "9434636208235322685476",
  "carrier": "FedEx",
  "status": "In Transit",
  "estimated_delivery": "2026-04-03",
  "events": [
    {"timestamp": "...", "location": "Memphis, TN", "description": "Departed facility"}
  ]
}
```

**Design note:** The tracking endpoint requires `ShipmentId` at the XML root level (not inside `ShipTransaction/Shipment`). There is no API to look up a ShipmentId by tracking number.

### 3.4 `void_shipment`

Cancel/void a shipping label.

**Endpoint:** `POST /shipmentservice.svc/shipment/void`

**Input:** `shipment_id` (ShipRush internal UUID)

**Output:**
```json
{
  "shipment_id": "c05d8af6-...",
  "voided": true,
  "message": null
}
```

**Design note:** The void endpoint requires `ShipmentId` inside `ShipTransaction/Shipment` (different structure from tracking). Only shipped labels can be voided — pending shipments return "not shipped or already voided".

### Removed: `validate_address`

ShipRush does not expose address validation as a standalone REST API endpoint (returns 404). Address validation is performed internally as part of the shipping flow.

---

## 4. ShipRush API Findings

These are the critical learnings from live API testing that informed the design.

### Carrier Codes

ShipRush uses numeric enum values, not string names:

| Code | Carrier | Notes |
|------|---------|-------|
| `0` | UPS | |
| `1` | FedEx | |
| `2` | DHL | |
| `3` | USPS (direct) | |
| `17` | ShipRush USPS | SR-prefixed accounts use this, not `3` |

The rate shopping response does NOT include a carrier code — it's auto-detected from service code patterns (e.g., `USPSGNDADV` -> `17`, `FedExGround` -> `1`).

### XML Quirks

- **`UPSServiceType`** is the element name for ALL carriers, not just UPS
- **`ShipmentNumber`** contains the tracking number (not `TrackingNumber`)
- Error severity can be `error` or `ERROR` (case-insensitive check needed)
- Valid responses return HTTP 200 even on business errors — check `<IsSuccess>` and `<ShippingMessage>` elements

### Endpoint Availability

| Endpoint | Exists | Notes |
|----------|--------|-------|
| `/shipment/rateshopping` | Yes | Multi-carrier rate comparison |
| `/shipment/rate` | Yes | Single-carrier rating (not used) |
| `/shipment/ship` | Yes | Label creation |
| `/shipment/tracking` | Yes | By ShipmentId only |
| `/shipment/void` | Yes | By ShipmentId only |
| `/shipment/lookup/services` | Yes | List service types for an account |
| `/address/validate` | **No** | 404 — not exposed |
| `/shipment/list` | **No** | 404 — no shipment search/listing |
| `/shipment/track` | **No** | 404 — wrong path (use `/tracking`) |

### Authentication

- Header: `X-SHIPRUSH-SHIPPING-TOKEN`
- Tokens generated in ShipRush Web > Settings > User Settings > Developer Tokens
- Tokens have a test mode flag (`IsTest`) that affects shipping behavior
- Token shown only once at creation — store securely

---

## 5. Project Structure

```
ShipRush-MCP/
├── server.py              # FastMCP entry point (4 tools)
├── config.py              # Env var config with .env support
├── requirements.txt       # Runtime dependencies
├── .env.example           # Template for environment variables
├── shiprush/
│   ├── client.py          # Async HTTP client (httpx)
│   ├── models.py          # Pydantic models
│   ├── xml_builder.py     # Build ShipRush XML requests
│   └── xml_parser.py      # Parse ShipRush XML responses
├── tests/
│   ├── test_client.py     # Client tests (mocked HTTP)
│   ├── test_models.py     # Model validation tests
│   ├── test_xml_builder.py # XML construction tests
│   ├── test_xml_parser.py # XML parsing tests
│   └── fixtures/          # Sample XML responses
└── docs/plans/            # This design doc
```

---

## 6. Configuration

### Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `SHIPRUSH_ENV` | No | `sandbox` | `sandbox` or `production` |
| `SHIPRUSH_SHIPPING_TOKEN_SANDBOX` | No | — | Token for sandbox API |
| `SHIPRUSH_SHIPPING_TOKEN_PRODUCTION` | No | — | Token for production API |
| `SHIPRUSH_SHIPPING_TOKEN` | Fallback | — | Used if env-specific token not set |
| `SHIPRUSH_BASE_URL` | No | Auto from env | Override API base URL |

---

## 7. Deployment

### AgentCore Runtime

```bash
pip install bedrock-agentcore-starter-toolkit

agentcore configure \
  --entrypoint server.py \
  --requirements-file requirements.txt \
  --protocol MCP \
  --name shiprush-mcp-server \
  --deployment-type container

agentcore launch --agent shiprush-mcp-server
```

### Future: AgentCore Gateway

When distributing to other teams/customers:
1. Register runtime as Gateway target
2. Add OAuth via Cognito/Auth0
3. Gateway handles routing, auth, and tool discovery

---

## 8. Research Sources

- [Deploy MCP servers in AgentCore Runtime](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-mcp.html)
- [MCP Protocol Contract](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-mcp-protocol-contract.html)
- [AgentCore MCP Getting Started](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/mcp-getting-started.html)
- [MCP Server Targets in Gateway](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-target-MCPservers.html)
- [From Local MCP Server to AWS in Two Commands](https://dev.to/aws/from-local-mcp-server-to-aws-deployment-in-two-commands-ag4)
- [ShipRush Web Non-Visual API Guide](https://docs.shiprush.com/en/for-developers/shipping/my-shiprush-shipping-web-non-visual-api-guide~7395985101005094591)
- [ShipRush Developer Portal](https://shiprush.com/developer/)
- [ShipRush ShipmentView Class](https://my.shiprush.com/ShipClassesDocs?typeName=ShipmentView)
- [ShipRush TCarrierType Enum](https://my.shiprush.com/ShipClassesDocs?typeName=TCarrierType)
