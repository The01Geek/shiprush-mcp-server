---
name: build-agentcore-mcp-server
description: Use when building an MCP server for a product API that will be deployed as a standalone service behind AWS Bedrock AgentCore Gateway. Covers FastMCP project scaffolding, AgentCore schema compliance, Docker containerization, App Runner deployment, Gateway target registration, and secret management.
---

# Build an AgentCore-Compatible MCP Server

## Overview

Step-by-step reference for building a Python MCP server using FastMCP, deploying it as a standalone HTTPS service (App Runner), and registering it as a target behind an AgentCore Gateway. This is the proven pattern used for the ShipRush MCP server and designed to be repeated for sister products (inventory, warehouse, etc.) that all feed into the same Gateway.

## Architecture

```
Claude Code / AI Agent
    | (IAM SigV4 via mcp-proxy-for-aws)
    v
AgentCore Gateway  <-- single MCP endpoint for ALL product tools
    | (HTTPS)          IAM inbound auth, semantic tool discovery
    |--- Target: ShipRush MCP Server   (App Runner)
    |--- Target: Inventory MCP Server  (App Runner / ECS / any HTTPS)
    |--- Target: Warehouse MCP Server  (App Runner / ECS / any HTTPS)
    v
Each standalone MCP server calls its own product API
```

**Key principle:** Each product team owns and deploys their own MCP server on their own infrastructure. The Gateway aggregates them all behind one endpoint. Agents discover tools from every server through a single connection.

## Project Structure

```
my-product-mcp/
  server.py              # FastMCP entry point with @mcp.tool() definitions
  config.py              # Token/config resolution (env vars + Secrets Manager)
  requirements.txt       # Python dependencies
  my_product/
    __init__.py
    client.py            # Async HTTP client for the product API (httpx)
    models.py            # Pydantic models for structured responses
    (parser/builder).py  # Request/response transformation (XML, JSON, etc.)
  tests/
    test_client.py
    test_models.py
    fixtures/            # Sample API responses for mocking
  .env.example           # Template for local dev environment
  .dockerignore
```

## Step 1: FastMCP Server (server.py)

### Minimal Skeleton

```python
"""Product MCP Server -- exposes product tools over MCP."""

import logging
import os

from mcp.server.fastmcp import FastMCP
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Receive, Scope, Send

log = logging.getLogger(__name__)

# --- Middleware for standalone deployments behind Gateway ---

class ApiKeyMiddleware:
    """Validate X-API-Key header when MCP_API_KEY env var is set."""

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


# --- MCP server ---

mcp = FastMCP(
    name="my-product-mcp-server",
    host="0.0.0.0",
    stateless_http=True,
)


@mcp.tool()
async def my_tool(
    param1: str,
    param2: float = 1.0,
    optional_param: str | None = None,
) -> dict:
    """Tool description for the agent. Be specific about what this does and what params mean."""
    # Call your product API here
    return {"result": "..."}


if __name__ == "__main__":
    if os.environ.get("DOCKER_CONTAINER"):
        import uvicorn
        app = mcp.streamable_http_app()
        if os.environ.get("STANDALONE"):
            app.add_middleware(ApiKeyMiddleware)
        uvicorn.run(app, host="0.0.0.0", port=8000)
    else:
        mcp.run(transport="streamable-http")
```

### Deployment Modes (controlled by env vars)

| Mode | Env Vars | Behavior |
|------|----------|----------|
| Local dev | (none) | `mcp.run()` on localhost |
| Standalone (App Runner/ECS) | `DOCKER_CONTAINER=1`, `STANDALONE=1` | uvicorn + ApiKeyMiddleware |
| AgentCore Runtime | `DOCKER_CONTAINER=1` | uvicorn + AgentCore Identity middleware |

## Step 2: AgentCore Schema Compliance (CRITICAL)

### No `$ref` in Tool Schemas

AgentCore Gateway and Runtime **reject** tool schemas containing `$ref`, `$defs`, `$anchor`, `$dynamicRef`, or `$dynamicAnchor`. This means:

**ALL tool parameters must be flat primitives.** No nested Pydantic models as tool arguments.

```python
# BAD - generates $ref in schema, REJECTED by AgentCore
class Address(BaseModel):
    street: str
    city: str
    state: str

@mcp.tool()
async def ship(origin: Address, destination: Address) -> dict: ...

# GOOD - flat primitives, no $ref
@mcp.tool()
async def ship(
    origin_street: str,
    origin_city: str,
    origin_state: str,
    destination_street: str,
    destination_city: str,
    destination_state: str,
) -> dict: ...
```

You CAN use Pydantic models internally (for validation, response shaping) -- just not as tool parameter types.

### Verify Your Schemas

After defining tools, verify no `$ref` appears:

```python
import json
app = mcp.streamable_http_app()
# Start server locally, then:
# curl -X POST http://localhost:8000/mcp -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
# Grep the response for "$ref" -- must find NONE.
```

### Other Schema Requirements

- Tool names: alphanumeric + underscores only
- Transport: streamable HTTP (`stateless_http=True`)
- Host: `0.0.0.0` (not `127.0.0.1`)
- Port: `8000` (AgentCore convention)
- Endpoint path: `/mcp` (FastMCP default)

## Step 3: Dependencies (requirements.txt)

```
mcp>=1.0
httpx>=0.27
pydantic>=2.0
python-dotenv>=1.0
uvicorn>=0.30
pytest>=8.0
pytest-asyncio>=0.24
```

Add `bedrock-agentcore-starter-toolkit` and `bedrock-agentcore` only if you also deploy to AgentCore Runtime.

## Step 4: Configuration (config.py)

```python
"""Product API configuration with layered token resolution."""

import os
from dotenv import load_dotenv

load_dotenv()

class ProductConfig:
    def __init__(self):
        self.base_url = os.environ.get("PRODUCT_API_URL", "https://api.example.com")
        self._token = os.environ.get("PRODUCT_API_TOKEN")

    @property
    def api_token(self) -> str:
        if not self._token:
            raise RuntimeError(
                "No API token available. Set PRODUCT_API_TOKEN env var "
                "or configure via Secrets Manager."
            )
        return self._token

config = ProductConfig()
```

For standalone deployments, tokens come from Secrets Manager via App Runner's `RuntimeEnvironmentSecrets` mapping (see Step 7).

## Step 5: Async HTTP Client (client.py)

```python
import httpx
from config import ProductConfig

class ProductClient:
    def __init__(self, config: ProductConfig):
        self._config = config
        self._http = httpx.AsyncClient(timeout=30.0)

    async def _get_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._config.api_token}",
            "Content-Type": "application/json",
        }

    async def some_operation(self, ...) -> dict:
        headers = await self._get_headers()
        resp = await self._http.post(
            f"{self._config.base_url}/endpoint",
            headers=headers,
            json={...},
        )
        resp.raise_for_status()
        return resp.json()
```

## Step 6: Dockerfile

Reuse the same Dockerfile pattern used by AgentCore's auto-generated Dockerfiles:

```dockerfile
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim
WORKDIR /app

ENV UV_SYSTEM_PYTHON=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_NO_PROGRESS=1 \
    PYTHONUNBUFFERED=1 \
    DOCKER_CONTAINER=1

COPY requirements.txt requirements.txt
RUN uv pip install -r requirements.txt

RUN useradd -m -u 1000 appuser
USER appuser

EXPOSE 8000

COPY . .

CMD ["python", "-m", "server"]
```

Build for x86_64 (App Runner default) or ARM64 depending on your target:

```bash
# x86_64 for App Runner
docker build --platform linux/amd64 -t my-product-mcp:latest .

# ARM64 for AgentCore Runtime (if also deploying there)
docker build --platform linux/arm64 -t my-product-mcp:arm64 .
```

### .dockerignore

```
.git/
.env
.venv/
__pycache__/
tests/
docs/
*.pyc
.pytest_cache/
.claude/
```

## Step 7: Deploy to App Runner

### Store Secrets

```python
import boto3

sm = boto3.client('secretsmanager', region_name='us-east-1')

sm.create_secret(
    Name='my-product-mcp/api-token',
    SecretString='your-product-api-token'
)
```

### Push Docker Image to ECR

```bash
ACCOUNT=your-aws-account-id
REGION=us-east-1
REPO=$ACCOUNT.dkr.ecr.$REGION.amazonaws.com/my-product-mcp

aws ecr create-repository --repository-name my-product-mcp --region $REGION
aws ecr get-login-password --region $REGION | docker login --username AWS --password-stdin $ACCOUNT.dkr.ecr.$REGION.amazonaws.com

docker tag my-product-mcp:latest $REPO:latest
docker push $REPO:latest
```

### Create IAM Roles

Two roles needed:

1. **ECR Access Role** (for App Runner to pull images):
   - Trust: `build.apprunner.amazonaws.com`
   - Policy: `AWSAppRunnerServicePolicyForECRAccess`

2. **Instance Role** (for Secrets Manager access):
   - Trust: `tasks.apprunner.amazonaws.com`
   - Policy: `secretsmanager:GetSecretValue` on your secret ARNs

### Create App Runner Service

```python
import boto3

apprunner = boto3.client('apprunner', region_name='us-east-1')

service = apprunner.create_service(
    ServiceName='my-product-mcp',
    SourceConfiguration={
        'ImageRepository': {
            'ImageIdentifier': f'{ACCOUNT}.dkr.ecr.{REGION}.amazonaws.com/my-product-mcp:latest',
            'ImageRepositoryType': 'ECR',
            'ImageConfiguration': {
                'Port': '8000',
                'RuntimeEnvironmentVariables': {
                    'DOCKER_CONTAINER': '1',
                    'STANDALONE': '1',
                },
                'RuntimeEnvironmentSecrets': {
                    'PRODUCT_API_TOKEN': 'arn:aws:secretsmanager:us-east-1:ACCOUNT:secret:my-product-mcp/api-token-XXXXXX',
                },
            },
        },
        'AutoDeploymentsEnabled': False,
        'AuthenticationConfiguration': {
            'AccessRoleArn': 'arn:aws:iam::ACCOUNT:role/AppRunnerECRAccessRole',
        },
    },
    InstanceConfiguration={
        'Cpu': '0.25 vCPU',
        'Memory': '0.5 GB',
        'InstanceRoleArn': 'arn:aws:iam::ACCOUNT:role/MyProductInstanceRole',
    },
    HealthCheckConfiguration={
        'Protocol': 'TCP',
        'Interval': 10,
        'Timeout': 5,
        'HealthyThreshold': 1,
        'UnhealthyThreshold': 5,
    },
)

service_url = f"https://{service['Service']['ServiceUrl']}"
```

Wait for status to become `RUNNING` before proceeding.

## Step 8: Register as Gateway Target

### If the Gateway Already Exists

Add your server as a new target to the existing Gateway:

```python
import boto3

client = boto3.client('bedrock-agentcore-control', region_name='us-east-1')

target = client.create_gateway_target(
    gatewayIdentifier='YOUR-GATEWAY-ID',
    name='my-product-mcp-server',
    description='My Product MCP server',
    targetConfiguration={
        'mcp': {
            'mcpServer': {
                'endpoint': 'https://YOUR-APP-RUNNER-URL.us-east-1.awsapprunner.com/mcp'
            }
        }
    }
)
# Wait for target status to be READY
```

The Gateway automatically calls `tools/list` on your server to discover and index all tools.

### If You Need to Create a New Gateway

```python
# 1. Create the Gateway with IAM auth
gateway = client.create_gateway(
    name='my-org-gateway',
    roleArn='arn:aws:iam::ACCOUNT:role/AgentCoreGatewayExecutionRole',
    protocolType='MCP',
    authorizerType='AWS_IAM',
    protocolConfiguration={
        'mcp': {
            'searchType': 'SEMANTIC'
        }
    }
)
# Wait for READY, then add targets as above.
```

The Gateway execution role needs:
- `bedrock-agentcore:*` on `arn:aws:bedrock-agentcore:*:*:*`
- `secretsmanager:GetSecretValue` on `*`
- `lambda:InvokeFunction` on `arn:aws:lambda:*:*:function:*` (if using Lambda targets)

### Gateway Name Rules

- **Hyphens allowed** (unlike Runtime agent names which require underscores)
- Pattern: `([0-9a-zA-Z][-]?){1,48}`

## Step 9: Connect Claude Code

```bash
claude mcp add my-product-gateway -s project -- \
  uvx mcp-proxy-for-aws@latest \
  "https://YOUR-GATEWAY-ID.gateway.bedrock-agentcore.REGION.amazonaws.com/mcp" \
  --service bedrock-agentcore \
  --region us-east-1
```

This generates a `.mcp.json`:
```json
{
  "mcpServers": {
    "my-product-gateway": {
      "type": "stdio",
      "command": "uvx",
      "args": [
        "mcp-proxy-for-aws@latest",
        "https://YOUR-GATEWAY-ID.gateway.bedrock-agentcore.REGION.amazonaws.com/mcp",
        "--service", "bedrock-agentcore",
        "--region", "us-east-1"
      ],
      "env": {}
    }
  }
}
```

If multiple product MCP servers are registered on the same Gateway, Claude Code sees ALL tools from ALL servers through this single connection.

## Known Issues and Gotchas

### Gateway Cannot Use AgentCore Runtime as mcpServer Target

**Bug:** Gateway outbound auth for `mcpServer` targets only supports OAuth2 or NoAuth. AgentCore Runtime requires SigV4 for its invocation endpoint. `GATEWAY_IAM_ROLE` credential type exists but is explicitly blocked for mcpServer targets. The OAuth/JWT workaround has a [known bug](https://github.com/awslabs/amazon-bedrock-agentcore-samples/issues/1030) where requests never reach the container.

**Workaround:** Deploy MCP servers as standalone services (App Runner, ECS, etc.) that the Gateway can reach over plain HTTPS.

### Gateway mcpServer Target Auth Limitations

For `mcpServer` targets, only these outbound credential types work:
- **NoAuth** (no credential provider) -- Gateway sends requests without auth
- **OAuth2** -- requires Cognito M2M setup

`GATEWAY_IAM_ROLE` and `API_KEY` credential types are rejected at the API level for mcpServer targets.

### App Runner Requires x86_64 Images

AgentCore Runtime uses ARM64 (Graviton). App Runner defaults to x86_64. Build with `--platform linux/amd64` for App Runner. Use `--platform linux/arm64` for AgentCore Runtime.

### Gateway Name vs Runtime Agent Name

- **Gateway names** accept hyphens: `my-gateway`
- **Runtime agent names** reject hyphens, require underscores: `my_agent`

### MCP Protocol Versions

Gateway supports MCP protocol versions `2025-06-18` and `2025-03-26`. Ensure your MCP SDK version produces compatible protocol responses.

### Gateway 5-Minute Timeout

Gateway has a 5-minute timeout per invocation. If your product API calls might exceed this, consider:
- Breaking long operations into multiple tools
- Returning a job ID and providing a separate status-check tool

### Semantic Search Tool

The Gateway automatically adds an `x_amz_bedrock_agentcore_search` tool. When many tools are registered, agents can use this to search for the right tool by natural language context. You don't need to implement this yourself.

### Tool Synchronization

Tools are discovered during `CreateGatewayTarget`. If you later add/remove tools from your server, trigger a re-sync:

```python
client.synchronize_gateway_targets(
    gatewayIdentifier='YOUR-GATEWAY-ID',
    targetIds=['YOUR-TARGET-ID']
)
```

## Testing Checklist

- [ ] `pytest tests/ -v` passes locally
- [ ] Server starts locally: `python server.py` and responds to `tools/list`
- [ ] Docker image builds for x86_64: `docker build --platform linux/amd64 ...`
- [ ] App Runner service reaches RUNNING state
- [ ] Gateway target reaches READY state (tools auto-discovered)
- [ ] Claude Code discovers tools via Gateway: restart Claude Code, verify tools appear
- [ ] End-to-end: ask Claude to use a tool, verify it calls the product API correctly

## Quick Reference

| What | Value |
|------|-------|
| Framework | FastMCP (`mcp.server.fastmcp.FastMCP`) |
| Transport | Streamable HTTP, stateless |
| Host/Port | `0.0.0.0:8000` |
| Endpoint path | `/mcp` |
| Schema constraint | No `$ref`, `$defs`, `$anchor` -- flat primitives only |
| Docker base | `ghcr.io/astral-sh/uv:python3.13-bookworm-slim` |
| App Runner arch | x86_64 (`--platform linux/amd64`) |
| Runtime arch | ARM64 (`--platform linux/arm64`) |
| Gateway auth inbound | `AWS_IAM` (SigV4 via mcp-proxy-for-aws) |
| Gateway auth outbound | NoAuth for mcpServer targets |
| Gateway timeout | 5 minutes per invocation |
| Claude Code proxy | `uvx mcp-proxy-for-aws@latest` with `--service bedrock-agentcore` |
