# ShipRush MCP Server — Design Document

**Date:** 2026-03-30
**Status:** Approved
**Approach:** Python FastMCP on AWS AgentCore Runtime

---

## 1. Overview

Build a reusable MCP server that wraps the ShipRush shipping REST API, exposing multi-carrier shipping operations as MCP tools. The server deploys to AWS Bedrock AgentCore Runtime as a stateless ARM64 container, enabling AI agents (Strands, Claude Code, Q CLI) to automate shipping workflows.

### Goals

- Expose 5 core ShipRush operations as MCP tools: rate, ship, track, void, address validation
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
|  |  +-- get_shipping_rates                       |  |
|  |  +-- create_shipment                          |  |
|  |  +-- track_shipment                           |  |
|  |  +-- void_shipment                            |  |
|  |  +-- validate_address                         |  |
|  |                                               |  |
|  |  ShipRush Client Layer (httpx async)           |  |
|  |  -> HTTPS -> ShipRush REST API                |  |
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

Get carrier rate quotes for a shipment.

**Input:**
| Field | Type | Required | Description |
|---|---|---|---|
| origin_address | Address | yes | Ship-from address |
| destination_address | Address | yes | Ship-to address |
| packages | Package[] | yes | One or more packages |
| carrier_filter | string | no | "fedex", "ups", "usps", or null for all |

**Output:**
```json
{
  "rates": [
    {
      "carrier": "fedex",
      "service_name": "FedEx Ground",
      "rate_amount": 12.50,
      "currency": "USD",
      "estimated_delivery_date": "2026-04-03"
    }
  ]
}
```

### 3.2 `create_shipment`

Create a shipment and generate a label.

**Input:**
| Field | Type | Required | Description |
|---|---|---|---|
| origin_address | Address | yes | Ship-from address |
| destination_address | Address | yes | Ship-to address |
| packages | Package[] | yes | One or more packages |
| carrier | string | yes | "fedex", "ups", or "usps" |
| service_name | string | yes | Service name from rate results |
| reference | string | no | Order ID or custom reference |

**Output:**
```json
{
  "tracking_number": "794644790132",
  "carrier": "fedex",
  "service_name": "FedEx Ground",
  "label_url": "https://...",
  "total_cost": 12.50,
  "currency": "USD"
}
```

### 3.3 `track_shipment`

Get tracking status and scan history.

**Input:**
| Field | Type | Required | Description |
|---|---|---|---|
| tracking_number | string | yes | Carrier tracking number |
| carrier | string | no | Helps disambiguation |

**Output:**
```json
{
  "tracking_number": "794644790132",
  "carrier": "fedex",
  "status": "In Transit",
  "estimated_delivery": "2026-04-03",
  "events": [
    {
      "timestamp": "2026-03-30T14:22:00Z",
      "location": "Memphis, TN",
      "description": "Departed FedEx facility"
    }
  ]
}
```

### 3.4 `void_shipment`

Cancel/void a shipment label.

**Input:**
| Field | Type | Required | Description |
|---|---|---|---|
| tracking_number | string | yes | Tracking number to void |
| carrier | string | no | Helps disambiguation |

**Output:**
```json
{
  "tracking_number": "794644790132",
  "voided": true,
  "message": "Shipment successfully voided"
}
```

### 3.5 `validate_address`

Validate and correct a shipping address.

**Input:**
| Field | Type | Required | Description |
|---|---|---|---|
| address | Address | yes | Address to validate |

**Output:**
```json
{
  "valid": true,
  "corrected_address": { "..." },
  "suggestions": [],
  "errors": []
}
```

### Shared Types

**Address:**
```
{name?: string, company?: string, street1: string, street2?: string,
 city: string, state: string, postal_code: string, country: string}
```

**Package:**
```
{weight_lb: float, length_in?: float, width_in?: float, height_in?: float}
```

These are inlined (not $ref'd) into each tool's JSON schema per AgentCore requirements.

### Error Handling

All tools return structured errors rather than throwing:
```json
{
  "error": "Invalid postal code",
  "code": "VALIDATION_ERROR"
}
```

Tool descriptions guide the LLM to chain tools naturally (e.g., "Call get_shipping_rates first to find available services, then pass carrier and service_name to create_shipment").

---

## 4. Project Structure

```
ShipRush-MCP/
├── server.py                  # FastMCP entry point, 5 tool definitions
├── shiprush/
│   ├── __init__.py
│   ├── client.py              # Async HTTP client for ShipRush REST API
│   ├── models.py              # Pydantic models (Address, Package, responses)
│   ├── xml_builder.py         # Build TShipment XML blocks from models
│   └── xml_parser.py          # Parse ShipRush XML responses into models
├── config.py                  # Env var loading (tokens, base URL)
├── requirements.txt           # mcp, httpx, pydantic, bedrock-agentcore-starter-toolkit
├── __init__.py
└── tests/
    ├── test_tools.py          # Integration tests against ShipRush sandbox
    ├── test_xml_builder.py    # Unit tests for XML serialization
    ├── test_xml_parser.py     # Unit tests for XML parsing
    └── fixtures/              # Sample XML responses from sandbox
```

### Module Responsibilities

- **`server.py`** — thin; declares tools with `@mcp.tool()`, delegates to `shiprush/client.py`
- **`shiprush/client.py`** — async `httpx` calls to ShipRush REST endpoints, sets auth headers
- **`shiprush/models.py`** — Pydantic models for all input/output schemas; generates JSON schemas for MCP
- **`shiprush/xml_builder.py`** — converts Pydantic models to ShipRush TShipment XML
- **`shiprush/xml_parser.py`** — converts ShipRush XML responses back to Pydantic models
- **`config.py`** — reads environment variables, provides typed config object

---

## 5. Configuration

### Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `SHIPRUSH_SHIPPING_TOKEN` | yes | — | X-SHIPRUSH-SHIPPING-TOKEN value |
| `SHIPRUSH_BASE_URL` | no | `https://sandbox.api.my.shiprush.com` | API base URL. Set to `https://api.my.shiprush.com` for production |

### Dependencies (requirements.txt)

```
mcp>=1.0
httpx>=0.27
pydantic>=2.0
bedrock-agentcore-starter-toolkit
```

---

## 6. Deployment

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Set token
export SHIPRUSH_SHIPPING_TOKEN="your-sandbox-token"

# Run locally
python server.py

# Test with MCP Inspector
npx @modelcontextprotocol/inspector
# Connect to http://localhost:8000/mcp
```

### AgentCore Runtime Deployment

```bash
# Step 1: Configure (generates Dockerfile, IAM roles, ECR repo)
agentcore configure \
  --entrypoint server.py \
  --requirements-file requirements.txt \
  --protocol MCP \
  --name shiprush-mcp-server \
  --disable-memory --disable-otel \
  --deployment-type container

# Step 2: Deploy (builds ARM64 container, pushes to ECR, launches)
agentcore launch --agent shiprush-mcp-server

# Output: arn:aws:bedrock-agentcore:{region}:{account}:runtime/shiprush-mcp-server-xxxxx
```

### Cleanup

```bash
agentcore destroy --agent shiprush-mcp-server
```

---

## 7. Testing Strategy

| Phase | Command / Method | What It Validates |
|---|---|---|
| **Unit tests** | `pytest tests/test_xml_builder.py tests/test_xml_parser.py` | XML serialization, model validation |
| **Local integration** | MCP Inspector at `localhost:8000/mcp` | All 5 tools against ShipRush sandbox |
| **Deployed smoke test** | `aws bedrock-agentcore invoke-agent-runtime` with `tools/list` and `tools/call` | Container health, tool discovery, basic execution |
| **Agent E2E** | Strands Agent with MCPClient pointing at runtime ARN | Full workflow: rate -> ship -> track |

### Sandbox Endpoints

- Base URL: `https://sandbox.api.my.shiprush.com`
- Rate endpoint: `/shipmentservice.svc/shipment/rate`
- Ship endpoint: `/shipmentservice.svc/shipment/ship`
- Auth header: `X-SHIPRUSH-SHIPPING-TOKEN: {token}`

---

## 8. Future Evolution (not in v1)

| Capability | When | What Changes |
|---|---|---|
| **AgentCore Gateway** | When distributing to other teams/customers | Register runtime as Gateway target, add OAuth via Cognito |
| **Multi-tenant** | When serving multiple ShipRush accounts | Per-request token passing or lookup from Secrets Manager |
| **Stateful mode** | If interactive workflows needed | Set `stateless_http=False`, add elicitation for rate selection |
| **Self-hosted (Approach C)** | If needed outside AgentCore | Same server.py, custom Dockerfile, deploy to ECS/EC2 |
| **Batch operations** | If bulk shipping needed | Add `create_shipments_batch` tool |

---

## 9. Research Sources

- [Deploy MCP servers in AgentCore Runtime](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-mcp.html)
- [MCP Protocol Contract](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-mcp-protocol-contract.html)
- [AgentCore MCP Getting Started](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/mcp-getting-started.html)
- [MCP Server Targets in Gateway](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-target-MCPservers.html)
- [From Local MCP Server to AWS in Two Commands](https://dev.to/aws/from-local-mcp-server-to-aws-deployment-in-two-commands-ag4)
- [AgentCore Runtime Stateful MCP Features](https://aws.amazon.com/about-aws/whats-new/2026/03/amazon-bedrock-agentcore-runtime-stateful-mcp/)
- [ShipRush Web Non-Visual API Guide](https://docs.shiprush.com/en/for-developers/shipping/my-shiprush-shipping-web-non-visual-api-guide~7395985101005094591)
- [ShipRush Developer Portal](https://shiprush.com/developer/)
- [ShipRush SOAP API](https://shiprush.com/web-service/)
