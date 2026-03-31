# Deploying ShipRush MCP Server to AWS AgentCore Runtime

Step-by-step guide for deploying this MCP server to Amazon Bedrock AgentCore Runtime. Written during the first deployment on 2026-03-31.

---

## Prerequisites

Before you begin, ensure you have:

1. **AWS Account** with Bedrock AgentCore access
2. **AWS CLI** installed and configured with credentials:
   ```bash
   aws configure
   # Enter your Access Key ID, Secret Access Key, region (us-east-1), output format (json)

   # Verify it works:
   aws sts get-caller-identity
   ```
3. **Python 3.11+** installed
4. **pip packages** installed:
   ```bash
   pip install mcp httpx pydantic python-dotenv bedrock-agentcore-starter-toolkit
   ```
5. **ShipRush Shipping Token** — from ShipRush Web > Settings > User Settings > Developer Tokens
6. **Docker is NOT required** — the toolkit uses AWS CodeBuild for remote ARM64 builds

### IAM Permissions

Your AWS user/role needs permissions to:
- Create and manage AgentCore Runtimes (`bedrock-agentcore:*`)
- Create IAM roles (`iam:CreateRole`, `iam:AttachRolePolicy`, `iam:PassRole`)
- Create ECR repositories and push images (`ecr:*`)
- Create CodeBuild projects (`codebuild:*`)

The simplest option for dev/testing: attach the **`BedrockAgentCoreFullAccess`** managed policy to your IAM user. For production, create a scoped-down policy.

---

## Step 1: Configure the Deployment

The `agentcore configure` command scans your project and generates deployment artifacts.

**What it creates:**
- `.bedrock_agentcore.yaml` — deployment config (entrypoint, protocol, IAM roles, ECR repo)
- `.bedrock_agentcore/shiprush_mcp_server/Dockerfile` — ARM64 container definition
- `.dockerignore` — prevents `.env`, `.git/`, `tests/`, `docs/` from being copied into the container

**Important: Agent names must use underscores, not hyphens.** The toolkit validates names and rejects hyphens.

**On Windows:** Prefix with `PYTHONIOENCODING=utf-8` to avoid emoji encoding errors in terminal output.

**Run from the project root:**

```bash
cd /path/to/ShipRush-MCP

# On Windows (bash/Git Bash):
PYTHONIOENCODING=utf-8 agentcore configure \
  --entrypoint server.py \
  --requirements-file requirements.txt \
  --protocol MCP \
  --name shiprush_mcp_server \
  --deployment-type container \
  --disable-memory --disable-otel \
  --region us-east-1 \
  --non-interactive

# On macOS/Linux:
agentcore configure \
  --entrypoint server.py \
  --requirements-file requirements.txt \
  --protocol MCP \
  --name shiprush_mcp_server \
  --deployment-type container \
  --disable-memory --disable-otel \
  --region us-east-1 \
  --non-interactive
```

**Flags explained:**
| Flag | Purpose |
|------|---------|
| `--entrypoint server.py` | The Python file that starts the MCP server |
| `--requirements-file requirements.txt` | Dependencies to install in the container |
| `--protocol MCP` | Tells AgentCore this is an MCP server (not a generic agent) |
| `--name shiprush_mcp_server` | Name for the deployment (**underscores only**, no hyphens) |
| `--deployment-type container` | Deploy as a container (vs. direct code deploy) |
| `--disable-memory` | Skip AgentCore Memory integration (not needed) |
| `--disable-otel` | Skip OpenTelemetry tracing (not needed for v1) |
| `--region us-east-1` | AWS region to deploy to |
| `--non-interactive` | Auto-create IAM roles and ECR repos without prompting |

**What happens behind the scenes:**
1. Validates the agent name (must be alphanumeric + underscores)
2. Marks IAM Execution Role for auto-creation (created during deploy, not now)
3. Marks ECR repository for auto-creation (created during deploy, not now)
4. Generates a Dockerfile using `ghcr.io/astral-sh/uv:python3.13-bookworm-slim` as the base image
5. The Dockerfile installs dependencies via `uv pip install -r requirements.txt`
6. The container runs as a non-root user (`bedrock_agentcore`, uid 1000)
7. Exposes ports 8000, 8080, 9000
8. Entry command: `python -m server`
9. Writes all config to `.bedrock_agentcore.yaml`

**Expected output:**
```
Configuration Success
Agent Name: shiprush_mcp_server
Deployment: container
Region: us-east-1
Account: YOUR_ACCOUNT_ID
Execution Role: Auto-create
ECR Repository: Auto-create
Authorization: IAM (default)
Memory: Disabled
```

**Warning you'll see on Windows/x86:**
> Platform mismatch: Current system is 'linux/amd64' but Bedrock AgentCore requires 'linux/arm64'

This is expected — the default `agentcore deploy` command does a remote cross-platform build via CodeBuild. You don't need a local ARM64 machine.

### Generated Files

**`.bedrock_agentcore.yaml`** — Key fields:
```yaml
agents:
  shiprush_mcp_server:
    entrypoint: server.py
    deployment_type: container
    platform: linux/arm64
    aws:
      execution_role: null           # auto-created on deploy
      execution_role_auto_create: true
      region: us-east-1
      ecr_repository: null           # auto-created on deploy
      ecr_auto_create: true
      protocol_configuration:
        server_protocol: MCP
```

**`.bedrock_agentcore/shiprush_mcp_server/Dockerfile`** — Auto-generated, uses `uv` for fast installs. You generally don't need to edit this.

**`.dockerignore`** — Auto-generated with sensible defaults. Already excludes `.env`, `.git/`, `tests/`, `docs/`. Add `.claude/` if present.

---

## Step 2: Store the ShipRush Token in AgentCore Identity

AgentCore Identity provides a secure vault (backed by AWS Secrets Manager) for API keys. The MCP server reads the token from this vault at runtime — no env vars or CLI flags needed.

**Store the token via Python SDK:**

```python
from bedrock_agentcore.services.identity import IdentityClient

client = IdentityClient("us-east-1")  # match your deployment region
result = client.create_api_key_credential_provider({
    "name": "shiprush",              # must match AGENTCORE_CREDENTIAL_NAME in config.py
    "apiKey": "your-shiprush-shipping-token"
})
print("Created:", result["credentialProviderArn"])
```

**Verify in AWS Console:** Go to Amazon Bedrock > AgentCore > Identity tab. You should see the `shiprush` credential provider listed.

**Why this is better than `--env` flags:**

| | `--env` flag | AgentCore Identity |
|---|---|---|
| **Storage** | Container env var | AWS Secrets Manager vault |
| **Visibility** | Shell history, process env | AWS Console Identity tab |
| **Rotation** | Redeploy required | Update in console, no redeploy |
| **Access control** | Anyone with container access | Scoped by workload identity |
| **Audit** | None | CloudTrail |

**How the server reads it at runtime:** The server's `config.py` uses the `@requires_api_key` decorator from the AgentCore SDK to fetch the token from the vault when running in AgentCore. When running locally, it falls back to environment variables from `.env`.

---

## Step 3: Deploy to AWS

```bash
PYTHONIOENCODING=utf-8 agentcore deploy \
  --agent shiprush_mcp_server \
  --env SHIPRUSH_ENV=production
```

Note: `SHIPRUSH_ENV=production` tells the server which ShipRush base URL to use. The actual API token comes from AgentCore Identity, not from `--env`.

**What happens:**
1. Creates the IAM Execution Role (`AmazonBedrockAgentCoreSDKRuntime-us-east-1-{hash}`) with:
   - Trust policy for `bedrock-agentcore.amazonaws.com`
   - Permissions for ECR, CloudWatch, X-Ray, Bedrock
2. Creates an ECR repository (e.g., `bedrock-agentcore/shiprush_mcp_server`)
3. Creates an AWS CodeBuild project for ARM64 builds
4. Uploads your source code to an S3 bucket
5. CodeBuild builds the ARM64 Docker container (~25-60 seconds)
6. Pushes the image to ECR
7. Creates an AgentCore Runtime instance with the container
8. At runtime, the server fetches the ShipRush token from AgentCore Identity vault
9. Returns the runtime ARN

**Expected output:**
```
arn:aws:bedrock-agentcore:us-east-1:123456789012:runtime/shiprush_mcp_server-xxxxx
```

**Save this ARN** — you'll need it for testing, integration, and cleanup.

### What if deploy fails?

Common issues:
- **"Access Denied"** — your IAM user needs `BedrockAgentCoreFullAccess` or equivalent
- **"ConflictException"** — agent already exists. Add `--auto-update-on-conflict` flag
- **CodeBuild timeout** — check CodeBuild logs in AWS Console > CodeBuild > Build projects
- **Container startup failure** — check CloudWatch Logs for the runtime name

---

## Step 4: Verify the Deployment

### Option A: AWS CLI smoke test

```bash
export SERVER_ARN="arn:aws:bedrock-agentcore:us-east-1:YOUR_ACCOUNT:runtime/shiprush_mcp_server-xxxxx"

# List tools
aws bedrock-agentcore invoke-agent-runtime \
  --agent-runtime-arn $SERVER_ARN \
  --content-type "application/json" \
  --accept "application/json, text/event-stream" \
  --payload '{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}' \
  --region us-east-1 \
  output.txt

cat output.txt
```

Expected: JSON listing 4 tools (get_shipping_rates, create_shipment, track_shipment, void_shipment)

### Option B: MCP Inspector

```bash
npx @modelcontextprotocol/inspector
```

Connect to the remote URL (requires auth):
```
https://bedrock-agentcore.us-east-1.amazonaws.com/runtimes/{ENCODED_ARN}/invocations?qualifier=DEFAULT
```

### Option C: Python MCP client

```python
import asyncio
import os
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

async def main():
    arn = os.getenv("SERVER_ARN")
    encoded = arn.replace(":", "%3A").replace("/", "%2F")
    url = f"https://bedrock-agentcore.us-east-1.amazonaws.com/runtimes/{encoded}/invocations?qualifier=DEFAULT"

    headers = {"Content-Type": "application/json"}
    # For SigV4 auth, use the aws_iam_streamablehttp_client instead

    async with streamablehttp_client(url, headers, timeout=120, terminate_on_close=False) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print(tools)

asyncio.run(main())
```

---

## Step 5: Connect Claude Code to the Deployed Server

Claude Code can't speak SigV4 natively, so AWS provides [`mcp-proxy-for-aws`](https://github.com/aws/mcp-proxy-for-aws) — a local stdio proxy that signs requests with your AWS credentials and forwards them to AgentCore.

**How it works:**
```
Claude Code  --stdio-->  mcp-proxy-for-aws  --SigV4/HTTPS-->  AgentCore Runtime
                         (local proxy)                         (your MCP server)
```

### Step 4a: Construct the endpoint URL

The URL format is:
```
https://bedrock-agentcore.{REGION}.amazonaws.com/runtimes/{ENCODED_ARN}/invocations?qualifier=DEFAULT
```

URL-encode the ARN (replace `:` with `%3A` and `/` with `%2F`):
```bash
ARN="arn:aws:bedrock-agentcore:us-east-1:YOUR_ACCOUNT:runtime/shiprush_mcp_server-XXXXX"
ENCODED=$(echo "$ARN" | sed 's/:/%3A/g; s/\//%2F/g')
ENDPOINT="https://bedrock-agentcore.us-east-1.amazonaws.com/runtimes/${ENCODED}/invocations?qualifier=DEFAULT"
echo "$ENDPOINT"
```

### Step 4b: Add to Claude Code

```bash
claude mcp add shiprush-agentcore -s project -- \
  uvx mcp-proxy-for-aws@latest \
  "$ENDPOINT" \
  --service bedrock-agentcore \
  --region us-east-1
```

This creates a `.mcp.json` file in your project:
```json
{
  "mcpServers": {
    "shiprush-agentcore": {
      "type": "stdio",
      "command": "uvx",
      "args": [
        "mcp-proxy-for-aws@latest",
        "https://bedrock-agentcore.us-east-1.amazonaws.com/runtimes/{ENCODED_ARN}/invocations?qualifier=DEFAULT",
        "--service", "bedrock-agentcore",
        "--region", "us-east-1"
      ],
      "env": {}
    }
  }
}
```

### Step 4c: Restart Claude Code and test

After adding, restart Claude Code (or start a new conversation). You should see `shiprush-agentcore` in the available MCP servers. Then you can ask Claude naturally:

> "Get me shipping rates for a 2 lb package from 100 Main St, Seattle WA 98101 to 200 Broadway, New York NY 10001"

Claude will call `get_shipping_rates` on your deployed AgentCore server and return the results.

**Prerequisites:**
- AWS credentials configured locally (`aws configure` or `AWS_PROFILE`)
- `uvx` available (comes with `uv` — install via `pip install uv` if needed)
- First run may take ~10 seconds as `uvx` downloads the proxy package

---

## Step 6: Integrate with Agents

### With Strands Agent (recommended for AgentCore)

```python
from strands import Agent
from strands.tools.mcp import MCPClient
from mcp_proxy_for_aws.client import aws_iam_streamablehttp_client

REGION = "us-east-1"
ACCOUNT_ID = "YOUR_ACCOUNT_ID"
RUNTIME_ID = "shiprush_mcp_server-xxxxx"

url = f"https://bedrock-agentcore.{REGION}.amazonaws.com/runtimes/{RUNTIME_ID}/invocations?qualifier=DEFAULT&accountId={ACCOUNT_ID}"

mcp_client_factory = lambda: aws_iam_streamablehttp_client(
    aws_service="bedrock-agentcore",
    aws_region=REGION,
    endpoint=url,
    terminate_on_close=False,
)

with MCPClient(mcp_client_factory) as mcp_client:
    tools = mcp_client.list_tools_sync()
    agent = Agent(tools=tools)
    agent("Ship a 2 lb package from Seattle to New York via the cheapest option")
```

### With Claude Code

Add to `~/.claude/mcp.json`:
```json
{
  "mcpServers": {
    "shiprush": {
      "type": "url",
      "url": "https://bedrock-agentcore.us-east-1.amazonaws.com/runtimes/{ENCODED_ARN}/invocations?qualifier=DEFAULT"
    }
  }
}
```

---

## Redeploying (Updates)

To push a new version of the server after code changes:

```bash
PYTHONIOENCODING=utf-8 agentcore deploy \
  --agent shiprush_mcp_server \
  --auto-update-on-conflict \
  --env SHIPRUSH_ENV=production
```

The `--auto-update-on-conflict` flag updates the existing runtime instead of failing with a conflict error. The ShipRush token doesn't need to be passed again — it's stored in AgentCore Identity.

---

## Cleanup

To destroy the deployment and stop charges:

```bash
PYTHONIOENCODING=utf-8 agentcore destroy --agent shiprush_mcp_server
```

This removes the AgentCore Runtime. It preserves:
- ECR images (delete manually via AWS Console > ECR if desired)
- IAM roles (delete manually if no longer needed)
- CodeBuild projects (delete manually if no longer needed)

---

## Troubleshooting

### "Access Denied" on configure/deploy
- Ensure your IAM user has `BedrockAgentCoreFullAccess` or equivalent permissions
- Check `aws sts get-caller-identity` returns the expected account
- For `iam:PassRole` errors, ensure your user can pass the auto-created execution role

### Agent name validation fails
- Names must use **underscores**, not hyphens: `shiprush_mcp_server` not `shiprush-mcp-server`
- Only alphanumeric characters and underscores allowed

### Windows encoding errors
- Prefix commands with `PYTHONIOENCODING=utf-8`
- The toolkit uses emoji characters that fail on Windows `cp1252` encoding

### Container fails to start
- Check CloudWatch Logs for the runtime (AWS Console > CloudWatch > Log Groups, search for agent name)
- Ensure `SHIPRUSH_SHIPPING_TOKEN_PRODUCTION` was passed via `--env`
- Verify the server starts locally: `python server.py`

### "Shipping token not found" from tools
- The credential provider wasn't created in AgentCore Identity
- Run the Python SDK snippet from Step 2 to create it
- Or fall back to `--env SHIPRUSH_SHIPPING_TOKEN_PRODUCTION=your-token` during deploy

### Platform mismatch warning
- Expected on Windows/x86 machines
- The default `agentcore deploy` uses CodeBuild for remote ARM64 builds — no local Docker needed

### Tools return empty or unexpected results
- Test the same request locally (`python server.py` + curl) to isolate whether it's an API or deployment issue
- Check that the env var values in deploy match what works locally

---

## Architecture Notes

- **Container listens on** `0.0.0.0:8000/mcp` — this is the default path AgentCore expects
- **ARM64 architecture** — AgentCore Runtime uses Graviton instances
- **Stateless mode** — each request is independent, no session state
- **IAM auth (default)** — requests are authenticated via SigV4. Add Cognito OAuth later for external consumers
- **Base image** — `ghcr.io/astral-sh/uv:python3.13-bookworm-slim` (uses `uv` for fast dependency installs)
- **Non-root** — container runs as user `bedrock_agentcore` (uid 1000)
