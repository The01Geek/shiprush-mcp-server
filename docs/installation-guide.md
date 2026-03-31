# Installing the ShipRush MCP Server

Guide for end users who want to **connect to** a deployed ShipRush MCP server from Claude Code, Claude Desktop, or another MCP client. This guide does not cover deploying the server itself — see [agentcore-deployment-guide.md](agentcore-deployment-guide.md) for that.

---

## Prerequisites

You need three things:

1. **AWS credentials** with permission to invoke the AgentCore Gateway
2. **`uv`** (Python package runner) — used to run the `mcp-proxy-for-aws` SigV4 signing proxy
3. **The Gateway URL** — provided by whoever deployed the server

### 1. AWS Credentials

Your AWS IAM user or role needs this permission:

```json
{
  "Effect": "Allow",
  "Action": "bedrock-agentcore:InvokeGateway",
  "Resource": "arn:aws:bedrock-agentcore:us-east-1:ACCOUNT_ID:gateway/GATEWAY_ID"
}
```

Ask the server operator for the exact Gateway ARN, or use a broader policy like `bedrock-agentcore:Invoke*` for development.

Configure your credentials locally:

```bash
aws configure
# Enter: Access Key ID, Secret Access Key, Region (us-east-1), Output (json)

# Verify:
aws sts get-caller-identity
```

Alternatively, set the `AWS_PROFILE` environment variable if you use named profiles.

### 2. Install uv

`uv` provides `uvx`, which runs the signing proxy without a permanent install.

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# Or via pip
pip install uv
```

Verify: `uvx --version`

### 3. Gateway URL

The server operator will provide a URL in this format:

```
https://GATEWAY-ID.gateway.bedrock-agentcore.REGION.amazonaws.com/mcp
```

---

## Claude Code

### Option A: CLI command (recommended)

```bash
claude mcp add shiprush -s user -- \
  uvx mcp-proxy-for-aws@latest \
  "https://GATEWAY-ID.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp" \
  --service bedrock-agentcore \
  --region us-east-1
```

Use `-s user` to make it available in all projects, or `-s project` for just the current project.

### Option B: Manual config

Add to your MCP config file:

- **Per-project:** `.mcp.json` in the project root
- **Global:** `~/.claude/mcp.json`

```json
{
  "mcpServers": {
    "shiprush": {
      "type": "stdio",
      "command": "uvx",
      "args": [
        "mcp-proxy-for-aws@latest",
        "https://GATEWAY-ID.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp",
        "--service",
        "bedrock-agentcore",
        "--region",
        "us-east-1"
      ],
      "env": {}
    }
  }
}
```

### Verify

Start a new Claude Code session. You should see the ShipRush tools available. Try:

> "Get shipping rates for a 2 lb package from 100 Main St, Seattle WA 98101 to 200 Broadway, New York NY 10001"

---

## Claude Desktop

Add to your Claude Desktop config file:

- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "shiprush": {
      "command": "uvx",
      "args": [
        "mcp-proxy-for-aws@latest",
        "https://GATEWAY-ID.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp",
        "--service",
        "bedrock-agentcore",
        "--region",
        "us-east-1"
      ]
    }
  }
}
```

Restart Claude Desktop. The ShipRush tools should appear in the tools menu (hammer icon).

---

## Strands Agent (Python)

```python
from strands import Agent
from strands.models import BedrockModel
from strands.tools.mcp import MCPClient
from mcp_proxy_for_aws.client import aws_iam_streamablehttp_client

GATEWAY_URL = "https://GATEWAY-ID.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp"

mcp_factory = lambda: aws_iam_streamablehttp_client(
    endpoint=GATEWAY_URL,
    aws_region="us-east-1",
    aws_service="bedrock-agentcore",
)

model = BedrockModel(model_id="anthropic.claude-sonnet-4-20250514-v1:0")

with MCPClient(mcp_factory) as mcp_client:
    tools = mcp_client.list_tools_sync()
    agent = Agent(model=model, tools=tools)
    agent("Ship a 2 lb package from Seattle to New York via the cheapest option")
```

**Install dependencies:**

```bash
pip install strands-agents strands-agents-tools mcp-proxy-for-aws
```

---

## Any MCP Client (Generic)

The server uses **streamable HTTP** transport. Any MCP client that supports streamable HTTP can connect, but the Gateway endpoint requires **AWS SigV4 request signing**.

The simplest approach is to use `mcp-proxy-for-aws` as a stdio-to-HTTPS bridge:

```bash
uvx mcp-proxy-for-aws@latest \
  "https://GATEWAY-ID.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp" \
  --service bedrock-agentcore \
  --region us-east-1
```

This starts a local stdio MCP proxy. Point your MCP client at this process's stdin/stdout.

For programmatic use, the `mcp-proxy-for-aws` Python library provides `aws_iam_streamablehttp_client()`:

```python
from mcp import ClientSession
from mcp_proxy_for_aws.client import aws_iam_streamablehttp_client

async with aws_iam_streamablehttp_client(
    endpoint="https://GATEWAY-ID.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp",
    aws_region="us-east-1",
    aws_service="bedrock-agentcore",
) as (read_stream, write_stream, _):
    async with ClientSession(read_stream, write_stream) as session:
        await session.initialize()
        tools = await session.list_tools()
        result = await session.call_tool("shiprush-mcp-server___get_shipping_rates", {
            "origin_street1": "100 Main St",
            "origin_city": "Seattle",
            "origin_state": "WA",
            "origin_postal_code": "98101",
            "destination_street1": "200 Broadway",
            "destination_city": "New York",
            "destination_state": "NY",
            "destination_postal_code": "10001",
            "package_weight_lb": 2.0,
        })
```

---

## Tool Names

When connected through AgentCore Gateway, tool names are prefixed with the Gateway target name:

| Tool | Gateway Name |
|------|-------------|
| `get_shipping_rates` | `shiprush-mcp-server___get_shipping_rates` |
| `create_shipment` | `shiprush-mcp-server___create_shipment` |
| `track_shipment` | `shiprush-mcp-server___track_shipment` |
| `void_shipment` | `shiprush-mcp-server___void_shipment` |

The Gateway also provides a semantic search tool (`x_amz_bedrock_agentcore_search`) that helps agents find the right tool by natural language context when many tools are registered.

MCP clients like Claude Code and Claude Desktop handle this transparently — you just ask for what you want in natural language and the agent picks the right tool.

---

## Troubleshooting

### "Missing credentials" or "Unable to locate credentials"

AWS credentials are not configured. Run `aws configure` or set `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` environment variables.

### "Access Denied" or "Not authorized"

Your IAM user/role doesn't have `bedrock-agentcore:InvokeGateway` permission on the Gateway ARN. Ask the server operator to grant access.

### "uvx: command not found"

`uv` is not installed. See the [uv installation docs](https://docs.astral.sh/uv/getting-started/installation/).

### Tools don't appear in Claude Code/Desktop

- Restart the application after adding the config
- Check that the Gateway URL is correct
- Verify AWS credentials: `aws sts get-caller-identity`
- Check for typos in the JSON config (missing commas, wrong quotes)

### First request is slow (~10 seconds)

Normal on first use — `uvx` downloads the `mcp-proxy-for-aws` package. Subsequent requests are fast.

### "No ShipRush API token available"

This is a server-side error, not a client-side issue. Contact the server operator — their deployment is missing the ShipRush API token configuration.
