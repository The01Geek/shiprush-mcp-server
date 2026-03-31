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

## Step 2: Store the ShipRush Token and Create Workload Identity

AgentCore Identity provides a secure vault (backed by AWS Secrets Manager) for API keys, and a workload identity system that authorizes your server to access them.

### Step 2a: Store the API key

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

### Step 2b: Create a workload identity

The workload identity is a named entity that represents your MCP server. When AgentCore Runtime receives a request, it generates a workload access token using this identity, which the server uses to fetch the API key from the vault.

```bash
PYTHONIOENCODING=utf-8 agentcore identity create-workload-identity \
  --name shiprush_mcp_server
```

This registers the identity in AgentCore and saves it to `.bedrock_agentcore.yaml`.

**How the full chain works at runtime:**
```
Client request (with user-id) → AgentCore Runtime
  → Runtime fetches workload identity for the agent
  → Runtime calls GetWorkloadAccessTokenForUserId
  → Runtime injects WorkloadAccessToken header into container request
  → AgentCoreIdentityMiddleware (server.py) extracts the header
  → @requires_api_key decorator uses the token to call GetResourceApiKey
  → Decrypted ShipRush API key is returned to the server
```

**Why this is better than `--env` flags:**

| | `--env` flag | AgentCore Identity |
|---|---|---|
| **Storage** | Container env var | AWS Secrets Manager vault |
| **Visibility** | Shell history, process env | AWS Console Identity tab |
| **Rotation** | Redeploy required | Update in console, no redeploy |
| **Access control** | Anyone with container access | Scoped by workload identity |
| **Audit** | None | CloudTrail |

**Fallback:** If the vault fetch fails (no workload identity, or caller didn't provide a user-id), the server falls back to the `SHIPRUSH_SHIPPING_TOKEN_PRODUCTION` env var if one was passed via `--env`.

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

### Option A: agentcore invoke (recommended)

```bash
# List tools (no user-id needed for tools/list)
PYTHONIOENCODING=utf-8 agentcore invoke \
  '{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}' \
  --agent shiprush_mcp_server

# Test rate shopping (requires --user-id for Identity vault access)
PYTHONIOENCODING=utf-8 agentcore invoke \
  '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"get_shipping_rates","arguments":{"origin_street1":"100 Main St","origin_city":"Seattle","origin_state":"WA","origin_postal_code":"98101","destination_street1":"200 Broadway","destination_city":"New York","destination_state":"NY","destination_postal_code":"10001","package_weight_lb":1.0}}}' \
  --agent shiprush_mcp_server \
  --user-id test-user
```

**Important:** The `--user-id` flag is required for tool calls that access the Identity vault. Without it, AgentCore Runtime won't generate the workload access token, and the token fetch will fail.

Expected: JSON with shipping rates ($9.46, $12.48, $51.65 for USPS services)

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

---

## AgentCore Gateway Integration

AgentCore Gateway provides a single MCP endpoint that aggregates tools from multiple backend MCP servers. This is the recommended architecture when you have more than one MCP server (e.g., ShipRush + inventory + warehouse systems), as it gives you unified tool discovery, semantic search, and centralized authentication.

### Architecture

```
Claude Code / Agent
    │ (IAM SigV4)
    ▼
AgentCore Gateway  ─── single MCP endpoint
    │ (HTTPS)          (semantic tool discovery, IAM auth)
    ▼
Standalone MCP Server  ─── App Runner / ECS / any infrastructure
    │ (HTTPS)               (each product team owns their deployment)
    ▼
ShipRush REST API
```

### Why Standalone Instead of Runtime-as-Target?

We initially attempted to add the AgentCore Runtime (where the MCP server was already deployed) as a Gateway `mcpServer` target. This failed due to an authentication gap:

- **Gateway outbound auth** for `mcpServer` targets only supports **OAuth2 or NoAuth** — not IAM/SigV4.
- **AgentCore Runtime** requires SigV4 for its invocation endpoint.
- The `GATEWAY_IAM_ROLE` credential provider type exists but is explicitly blocked for `mcpServer` targets (API validation error).
- The OAuth/JWT workaround has a [known bug (issue #1030)](https://github.com/awslabs/amazon-bedrock-agentcore-samples/issues/1030) where JWT-authenticated requests reach the Runtime but are never forwarded to the container.

We chose to deploy the MCP server as a **standalone service on AWS App Runner** for two reasons:

1. **It works reliably** — the Gateway can reach a public HTTPS endpoint without the SigV4/IAM constraint.
2. **It reflects a realistic enterprise pattern** — in a multi-product organization, each team (shipping, inventory, warehouse) would host their MCP server on their own infrastructure, not necessarily on AgentCore Runtime. The Gateway aggregates them all behind one endpoint.

### Step-by-Step: Gateway + Standalone Server

#### Prerequisites

- An existing AgentCore deployment (Steps 1-5 above)
- Docker installed locally (for building x86_64 images)
- The ShipRush shipping token stored in AWS Secrets Manager

#### 1. Create the Gateway

```python
import boto3

client = boto3.client('bedrock-agentcore-control', region_name='us-east-1')

gateway = client.create_gateway(
    name='shiprush-gateway',
    roleArn='arn:aws:iam::YOUR_ACCOUNT:role/AgentCoreGatewayExecutionRole',
    protocolType='MCP',
    authorizerType='AWS_IAM',
    protocolConfiguration={
        'mcp': {
            'searchType': 'SEMANTIC'
        }
    }
)

print(f"Gateway URL: {gateway['gatewayUrl']}")
print(f"Gateway ARN: {gateway['gatewayArn']}")
```

If you don't have a Gateway execution role, the `agentcore` CLI can create one:

```bash
# This auto-creates an IAM role and fails on gateway creation (expected),
# but the role persists and can be used with boto3 above.
PYTHONIOENCODING=utf-8 agentcore gateway create-mcp-gateway \
  --name shiprush-gateway \
  --region us-east-1
```

The Gateway role needs these policies:
- `bedrock-agentcore:*` on `arn:aws:bedrock-agentcore:*:*:*`
- `secretsmanager:GetSecretValue` on `*`
- `lambda:InvokeFunction` on `arn:aws:lambda:*:*:function:*` (for Lambda targets)

#### 2. Build and Push the x86_64 Docker Image

The existing AgentCore image is ARM64 (Graviton). App Runner requires x86_64:

```bash
# Build for x86_64
docker build --platform linux/amd64 \
  -t shiprush-mcp-standalone:latest \
  -f .bedrock_agentcore/shiprush_mcp_server/Dockerfile .

# Login to ECR
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin \
  YOUR_ACCOUNT.dkr.ecr.us-east-1.amazonaws.com

# Tag and push
docker tag shiprush-mcp-standalone:latest \
  YOUR_ACCOUNT.dkr.ecr.us-east-1.amazonaws.com/bedrock-agentcore-shiprush_mcp_server:standalone-amd64
docker push \
  YOUR_ACCOUNT.dkr.ecr.us-east-1.amazonaws.com/bedrock-agentcore-shiprush_mcp_server:standalone-amd64
```

#### 3. Store Secrets in AWS Secrets Manager

```python
import boto3

sm = boto3.client('secretsmanager', region_name='us-east-1')

# Store the ShipRush shipping token
sm.create_secret(
    Name='shiprush-mcp/shipping-token',
    SecretString='your-shiprush-shipping-token'
)
```

#### 4. Create IAM Roles for App Runner

```python
import boto3, json

iam = boto3.client('iam')

# ECR access role (for pulling images)
iam.create_role(
    RoleName='AppRunnerECRAccessRole',
    AssumeRolePolicyDocument=json.dumps({
        'Version': '2012-10-17',
        'Statement': [{
            'Effect': 'Allow',
            'Principal': {'Service': 'build.apprunner.amazonaws.com'},
            'Action': 'sts:AssumeRole'
        }]
    })
)
iam.attach_role_policy(
    RoleName='AppRunnerECRAccessRole',
    PolicyArn='arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForECRAccess'
)

# Instance role (for Secrets Manager access)
iam.create_role(
    RoleName='AppRunnerShipRushInstanceRole',
    AssumeRolePolicyDocument=json.dumps({
        'Version': '2012-10-17',
        'Statement': [{
            'Effect': 'Allow',
            'Principal': {'Service': 'tasks.apprunner.amazonaws.com'},
            'Action': 'sts:AssumeRole'
        }]
    })
)
iam.put_role_policy(
    RoleName='AppRunnerShipRushInstanceRole',
    PolicyName='SecretsManagerAccess',
    PolicyDocument=json.dumps({
        'Version': '2012-10-17',
        'Statement': [{
            'Effect': 'Allow',
            'Action': ['secretsmanager:GetSecretValue'],
            'Resource': 'arn:aws:secretsmanager:us-east-1:YOUR_ACCOUNT:secret:shiprush-mcp/*'
        }]
    })
)
```

#### 5. Deploy to App Runner

```python
import boto3

apprunner = boto3.client('apprunner', region_name='us-east-1')

service = apprunner.create_service(
    ServiceName='shiprush-mcp-standalone',
    SourceConfiguration={
        'ImageRepository': {
            'ImageIdentifier': 'YOUR_ACCOUNT.dkr.ecr.us-east-1.amazonaws.com/bedrock-agentcore-shiprush_mcp_server:standalone-amd64',
            'ImageRepositoryType': 'ECR',
            'ImageConfiguration': {
                'Port': '8000',
                'RuntimeEnvironmentVariables': {
                    'DOCKER_CONTAINER': '1',
                    'STANDALONE': '1',
                    'SHIPRUSH_ENV': 'production',
                    'PYTHONUNBUFFERED': '1',
                },
                'RuntimeEnvironmentSecrets': {
                    'SHIPRUSH_SHIPPING_TOKEN_PRODUCTION': 'arn:aws:secretsmanager:us-east-1:YOUR_ACCOUNT:secret:shiprush-mcp/shipping-token-XXXXXX',
                },
            },
        },
        'AutoDeploymentsEnabled': False,
        'AuthenticationConfiguration': {
            'AccessRoleArn': 'arn:aws:iam::YOUR_ACCOUNT:role/AppRunnerECRAccessRole',
        },
    },
    InstanceConfiguration={
        'Cpu': '0.25 vCPU',
        'Memory': '0.5 GB',
        'InstanceRoleArn': 'arn:aws:iam::YOUR_ACCOUNT:role/AppRunnerShipRushInstanceRole',
    },
    HealthCheckConfiguration={
        'Protocol': 'TCP',
        'Interval': 10,
        'Timeout': 5,
        'HealthyThreshold': 1,
        'UnhealthyThreshold': 5,
    },
)

print(f"Service URL: https://{service['Service']['ServiceUrl']}")
```

Key environment variables:
| Variable | Purpose |
|----------|---------|
| `DOCKER_CONTAINER=1` | Tells server.py to run uvicorn |
| `STANDALONE=1` | Skips AgentCore Identity middleware |
| `SHIPRUSH_ENV=production` | Points to production ShipRush API |
| `SHIPRUSH_SHIPPING_TOKEN_PRODUCTION` | Token from Secrets Manager |

#### 6. Add as Gateway Target

```python
import boto3

client = boto3.client('bedrock-agentcore-control', region_name='us-east-1')

target = client.create_gateway_target(
    gatewayIdentifier='YOUR-GATEWAY-ID',
    name='shiprush-mcp-server',
    description='ShipRush MCP server (standalone on App Runner)',
    targetConfiguration={
        'mcp': {
            'mcpServer': {
                'endpoint': 'https://YOUR-APP-RUNNER-URL.us-east-1.awsapprunner.com/mcp'
            }
        }
    }
)
```

The Gateway automatically calls `tools/list` on the target to discover tools. Wait for the target status to be `READY`.

#### 7. Connect Claude Code to the Gateway

```bash
claude mcp add shiprush-gateway -s project -- \
  uvx mcp-proxy-for-aws@latest \
  "https://YOUR-GATEWAY-ID.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp" \
  --service bedrock-agentcore \
  --region us-east-1
```

This creates a `.mcp.json`:
```json
{
  "mcpServers": {
    "shiprush-gateway": {
      "type": "stdio",
      "command": "uvx",
      "args": [
        "mcp-proxy-for-aws@latest",
        "https://YOUR-GATEWAY-ID.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp",
        "--service", "bedrock-agentcore",
        "--region", "us-east-1"
      ],
      "env": {}
    }
  }
}
```

#### 8. Adding Future Sister Products

To add another MCP server (e.g., inventory) to the same Gateway:

```python
client.create_gateway_target(
    gatewayIdentifier='YOUR-GATEWAY-ID',
    name='inventory-mcp-server',
    description='Inventory management MCP server',
    targetConfiguration={
        'mcp': {
            'mcpServer': {
                'endpoint': 'https://inventory-mcp.your-domain.com/mcp'
            }
        }
    }
)
```

Claude Code automatically discovers all tools from all targets through the single Gateway endpoint. The Gateway's semantic search tool helps agents find the right tool from a large catalog.

### Gateway Security Note

In this setup, the Gateway provides IAM-based inbound authentication (Claude Code → Gateway via SigV4). The Gateway-to-standalone-server connection currently uses NoAuth because `mcpServer` targets only support OAuth2 or NoAuth for outbound credentials.

For production deployments, consider:
- **OAuth2 outbound auth** — configure Cognito M2M credentials for Gateway → server communication
- **Network-level security** — deploy the standalone server in a VPC and use VPC endpoints
- **Gateway interceptors** — add Lambda interceptors for fine-grained access control, PII redaction, or audit logging

### Gateway Cleanup

```python
import boto3

client = boto3.client('bedrock-agentcore-control', region_name='us-east-1')

# Delete target first
client.delete_gateway_target(
    gatewayIdentifier='YOUR-GATEWAY-ID',
    targetId='YOUR-TARGET-ID'
)

# Then delete gateway
client.delete_gateway(gatewayIdentifier='YOUR-GATEWAY-ID')

# Delete App Runner service
apprunner = boto3.client('apprunner', region_name='us-east-1')
apprunner.delete_service(ServiceArn='YOUR-APP-RUNNER-SERVICE-ARN')
```
