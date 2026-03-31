"""ShipRush API configuration.

Token resolution order:
1. Environment variables / .env file (immediate, for local dev and --env fallback)
2. AgentCore Identity vault (per-request, when workload identity is configured)

When deployed to AgentCore Runtime with a workload identity, the token is
fetched from the Identity vault on each request. The WorkloadAccessToken
header (injected by Runtime) is extracted by middleware in server.py and
stored in BedrockAgentCoreContext for the @requires_api_key decorator.
"""

import logging
import os

from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)

BASE_URLS = {
    "sandbox": "https://sandbox.api.my.shiprush.com",
    "production": "https://api.my.shiprush.com",
}

# Name of the credential provider in AgentCore Identity.
AGENTCORE_CREDENTIAL_NAME = "shiprush"


def _get_token_from_env() -> str | None:
    """Fetch the ShipRush token from environment variables."""
    env = os.environ.get("SHIPRUSH_ENV", "sandbox").lower()
    token_key = f"SHIPRUSH_SHIPPING_TOKEN_{env.upper()}"
    token = os.environ.get(token_key) or os.environ.get("SHIPRUSH_SHIPPING_TOKEN")
    if token:
        log.info("Loaded ShipRush token from environment variable")
    return token


async def get_token_from_agentcore() -> str | None:
    """Fetch the ShipRush token from AgentCore Identity vault.

    Must be called within an async request context where the
    AgentCoreIdentityMiddleware has set the workload access token.
    """
    try:
        from bedrock_agentcore.identity.auth import requires_api_key

        @requires_api_key(provider_name=AGENTCORE_CREDENTIAL_NAME)
        async def _fetch(*, api_key: str) -> str:
            return api_key

        token = await _fetch()
        log.info("Loaded ShipRush token from AgentCore Identity vault")
        return token
    except Exception as e:
        log.warning("AgentCore Identity vault fetch failed: %s: %s", type(e).__name__, e)
        return None


class ShipRushConfig:
    def __init__(self, static_token: str | None = None):
        self.env = os.environ.get("SHIPRUSH_ENV", "sandbox").lower()
        self._static_token = static_token
        self.base_url = os.environ.get(
            "SHIPRUSH_BASE_URL",
            BASE_URLS.get(self.env, BASE_URLS["sandbox"]),
        )

    @property
    def shipping_token(self) -> str:
        """Return the static token (from env var). Raises if none set."""
        if self._static_token:
            return self._static_token
        raise RuntimeError(
            "No static ShipRush API token available. Use get_shipping_token() for async vault access."
        )

    @property
    def has_static_token(self) -> bool:
        return self._static_token is not None

    async def get_shipping_token(self) -> str:
        """Resolve the ShipRush token. Uses env var if available, otherwise AgentCore Identity vault."""
        if self._static_token:
            return self._static_token
        token = await get_token_from_agentcore()
        if token:
            return token
        raise RuntimeError(
            "No ShipRush API token available. Either:\n"
            "  1. Set SHIPRUSH_SHIPPING_TOKEN_PRODUCTION in .env (local dev)\n"
            "  2. Pass --env SHIPRUSH_SHIPPING_TOKEN_PRODUCTION=... during deploy\n"
            "  3. Configure workload identity for AgentCore Identity vault"
        )


def _build_config() -> ShipRushConfig:
    """Build config at startup."""
    # If env var is set, use it (local dev or --env fallback)
    token = _get_token_from_env()
    if token:
        return ShipRushConfig(static_token=token)

    # No env var — assume workload identity will provide per-request
    if os.environ.get("DOCKER_CONTAINER"):
        log.info("No env token; will use AgentCore Identity vault per-request")
        return ShipRushConfig(static_token=None)

    raise RuntimeError(
        "Missing ShipRush API token. Either:\n"
        "  1. Set SHIPRUSH_SHIPPING_TOKEN_PRODUCTION or SHIPRUSH_SHIPPING_TOKEN in .env\n"
        "  2. Pass --env SHIPRUSH_SHIPPING_TOKEN_PRODUCTION=... during agentcore deploy\n"
        "  3. Deploy with workload identity for AgentCore Identity vault"
    )


config = _build_config()
