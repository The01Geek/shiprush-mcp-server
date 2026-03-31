# ShipRush MCP Server

A [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server that wraps the [Descartes ShipRush](https://shiprush.com/) shipping API, enabling AI agents to automate multi-carrier shipping workflows. Built with [FastMCP](https://github.com/modelcontextprotocol/python-sdk) (Python), deployable as a standalone service behind [AgentCore Gateway](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway.html) or directly on [AgentCore Runtime](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-mcp.html).

## Tools

The server exposes 4 tools that cover the core shipping workflow:

### `get_shipping_rates`

Rate-shop across all carriers configured in your ShipRush account. Returns available services with prices, transit times, and a `quote_id` for each option.

**Key parameters:** origin/destination addresses, package weight and dimensions, optional `carrier_filter`

**Returns:** List of rate options, each containing:
- `carrier` — numeric carrier code (e.g., `"17"` for ShipRush USPS)
- `service_name` — human-readable service name (e.g., "USPS Ground Advantage")
- `service_code` — ShipRush service type code (e.g., `"USPSGNDADV"`)
- `rate_amount` — total cost
- `transit_days` — estimated business days in transit
- `quote_id` — pass this to `create_shipment`
- `shipping_account_id` — pass this to `create_shipment`

### `create_shipment`

Create a shipment and generate a shipping label. Requires a `quote_id` from a prior `get_shipping_rates` call.

**Key parameters:** `quote_id` (required), `carrier`, `service_code`, `shipping_account_id` (all from the rate response), origin/destination addresses, package details, optional `reference`

**Returns:**
- `shipment_id` — ShipRush internal ID (needed for track/void)
- `tracking_number` — carrier tracking number
- `total_cost` — actual charge
- `label_url` — URL to the shipping label (when available)

### `track_shipment`

Get tracking status and scan history for a shipment.

**Key parameters:** `shipment_id` (from `create_shipment` response)

**Returns:** `shipment_id`, `tracking_number`, `carrier`, `status`, `estimated_delivery`, `events[]`

### `void_shipment`

Cancel/void a shipping label.

**Key parameters:** `shipment_id` (from `create_shipment` response)

**Returns:** `shipment_id`, `voided` (boolean), `message`

## Agent Workflow

The tools are designed to be chained in a natural sequence:

```
1. get_shipping_rates  -->  Pick the best rate
2. create_shipment     -->  Pass quote_id, carrier, service_code, shipping_account_id
3. track_shipment      -->  Pass shipment_id from step 2
4. void_shipment       -->  Pass shipment_id from step 2 (if needed)
```

An agent receiving "ship this 2 lb package from Seattle to New York via the cheapest option" would:
1. Call `get_shipping_rates` with the addresses and weight
2. Select the lowest `rate_amount` from the results
3. Call `create_shipment` with the selected rate's `quote_id`, `carrier`, `service_code`, and `shipping_account_id`
4. Return the `tracking_number` to the user

## Design Decisions

### Why flat parameters instead of nested objects?

AWS AgentCore requires tool JSON schemas to be **fully self-contained** with no `$ref`, `$defs`, or `$anchor` keywords. Passing nested Pydantic models as tool parameters would generate schemas with `$ref`. Flat parameters (all primitives) avoid this entirely.

### Why `shipment_id` instead of `tracking_number` for track/void?

The ShipRush REST API requires an internal `ShipmentId` (UUID) for the tracking and void endpoints. There is **no API endpoint to look up a ShipmentId by tracking number**. This means:
- `create_shipment` returns both `shipment_id` and `tracking_number`
- The agent must store the `shipment_id` if it needs to track or void later
- Users with only a tracking number must find the `ShipmentId` in the ShipRush dashboard

### Why `quote_id` instead of carrier/service for shipping?

ShipRush's ship endpoint works best with `ShipViaQuoteId=true` and a `ShipmentQuoteId` from the rate shopping response. This ensures the shipped rate matches the quoted rate. The carrier code and service code are still required by the API, so they're passed alongside the quote.

### Why no address validation tool?

ShipRush does not expose address validation as a standalone REST API endpoint (returns 404). Address validation is performed internally as part of the shipping flow within the ShipRush platform.

### Why numeric carrier codes?

The ShipRush API uses numeric enum values for carriers (e.g., `0` = UPS, `1` = FedEx, `17` = ShipRush USPS), not the string names. The server auto-detects the correct carrier code from the service type returned by rate shopping, so agents don't need to know the numeric mapping.

### Rate shopping vs. single-carrier rating

The server uses the `/shipment/rateshopping` endpoint (not `/shipment/rate`). Rate shopping returns rates across **all configured carriers** in one call, which is more useful for agents. Single-carrier rating requires specifying a carrier upfront and returns only one result.

## Connecting to a Deployed Server

If someone has already deployed the ShipRush MCP server and you just want to **use it** from Claude Code, Claude Desktop, or another MCP client, see [`docs/installation-guide.md`](docs/installation-guide.md).

## Setup (for developers)

### Prerequisites

- Python 3.11+
- A [ShipRush](https://shiprush.com/) account with at least one carrier configured
- A ShipRush Shipping Token (from ShipRush Web > Settings > User Settings > Developer Tokens)

### Installation

```bash
pip install -r requirements.txt
```

### Configuration

Create a `.env` file:

```env
SHIPRUSH_ENV=production

SHIPRUSH_SHIPPING_TOKEN_SANDBOX=your-sandbox-token
SHIPRUSH_SHIPPING_TOKEN_PRODUCTION=your-production-token
```

| Variable | Required | Description |
|----------|----------|-------------|
| `SHIPRUSH_ENV` | No | `sandbox` or `production` (default: `sandbox`) |
| `SHIPRUSH_SHIPPING_TOKEN_SANDBOX` | No | Token for `sandbox.api.my.shiprush.com` |
| `SHIPRUSH_SHIPPING_TOKEN_PRODUCTION` | No | Token for `api.my.shiprush.com` |
| `SHIPRUSH_SHIPPING_TOKEN` | No | Fallback token if env-specific token is not set |

### Running Locally

```bash
python server.py
```

The server starts on `http://localhost:8000/mcp` (streamable HTTP transport).

### Testing with MCP Inspector

```bash
npx @modelcontextprotocol/inspector
```

Connect to `http://localhost:8000/mcp` and call `tools/list` to see all 4 tools.

### Running Tests

```bash
pytest tests/ -v
```

## Deployment

The server supports three deployment modes. See [`docs/agentcore-deployment-guide.md`](docs/agentcore-deployment-guide.md) for the complete step-by-step guide.

### Recommended: AgentCore Gateway + Standalone Server

The preferred architecture for multi-product setups. The MCP server runs as a standalone service (App Runner, ECS, or any HTTPS endpoint), and AgentCore Gateway aggregates it with other MCP servers behind a single endpoint with IAM auth and semantic tool discovery.

```
Claude Code → (SigV4) → AgentCore Gateway → (HTTPS) → Standalone MCP Server → ShipRush API
                              ↳ → Inventory MCP Server (future)
                              ↳ → Warehouse MCP Server (future)
```

```bash
# Build and deploy standalone server to App Runner
docker build --platform linux/amd64 -t shiprush-mcp-standalone:latest \
  -f .bedrock_agentcore/shiprush_mcp_server/Dockerfile .

# Create Gateway and add the server as a target
# (see docs/agentcore-deployment-guide.md for full boto3 steps)

# Connect Claude Code to the Gateway
claude mcp add shiprush-gateway -s project -- \
  uvx mcp-proxy-for-aws@latest \
  "https://YOUR-GATEWAY-ID.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp" \
  --service bedrock-agentcore --region us-east-1
```

### Alternative: Direct AgentCore Runtime

For single-server deployments where Gateway aggregation isn't needed:

```bash
pip install bedrock-agentcore-starter-toolkit bedrock-agentcore

agentcore configure \
  --entrypoint server.py --requirements-file requirements.txt \
  --protocol MCP --name shiprush_mcp_server \
  --deployment-type container --disable-memory --disable-otel \
  --region us-east-1 --non-interactive

agentcore deploy --agent shiprush_mcp_server --env SHIPRUSH_ENV=production
```

The ShipRush token can be stored in the AgentCore Identity vault (backed by AWS Secrets Manager) or passed via environment variable.

### AgentCore Compliance

| Requirement | Status |
|-------------|--------|
| Streamable HTTP transport | Yes |
| Host `0.0.0.0:8000/mcp` | Yes |
| ARM64 container | Yes (via agentcore toolkit) |
| Stateless mode | Yes (`stateless_http=True`) |
| No `$ref` in tool schemas | Yes (flat parameters) |
| JSON-RPC format | Yes |

## Project Structure

```
ShipRush-MCP/
├── server.py              # FastMCP entry point (4 tools)
├── config.py              # Config: AgentCore Identity vault or .env fallback
├── requirements.txt
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
└── docs/plans/            # Design doc and implementation plan
```

## ShipRush API Reference

### Endpoints Used

| Operation | Endpoint | Method |
|-----------|----------|--------|
| Rate shopping | `/shipmentservice.svc/shipment/rateshopping` | POST |
| Create shipment | `/shipmentservice.svc/shipment/ship` | POST |
| Track shipment | `/shipmentservice.svc/shipment/tracking` | POST |
| Void shipment | `/shipmentservice.svc/shipment/void` | POST |

### Authentication

All requests require the `X-SHIPRUSH-SHIPPING-TOKEN` header. Tokens are generated in ShipRush Web > Settings > User Settings > Developer Tokens.

### Carrier Codes

| Code | Carrier |
|------|---------|
| `0` | UPS |
| `1` | FedEx |
| `2` | DHL |
| `3` | USPS (direct) |
| `17` | ShipRush USPS (SR-prefixed accounts) |

The server auto-detects carrier codes from service type patterns in rate responses.

### Known API Limitations

- **No shipment lookup by tracking number** — the API has no endpoint to search/list shipments or map a tracking number to a `ShipmentId`
- **No standalone address validation** — address validation is internal to the ship/rate flow
- **Carrier code required for shipping** — even when using `ShipViaQuoteId`, the `Carrier` element must be present
- **Rate shopping response lacks carrier type** — the carrier code is derived from service type patterns, not returned directly
- **XML-only** — the API uses XML request/response bodies (not JSON); the MCP server handles all XML serialization internally

## License

Private — for internal use.
