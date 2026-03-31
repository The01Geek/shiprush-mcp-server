"""ShipRush API configuration.

Token resolution order:
1. AgentCore Identity vault (when deployed with workload identity configured)
2. Environment variables / .env file (local dev and container fallback)
"""

import asyncio
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


def _get_token_from_agentcore() -> str | None:
    """Attempt to fetch the ShipRush token from AgentCore Identity vault."""
    if not os.environ.get("DOCKER_CONTAINER"):
        return None
    try:
        from bedrock_agentcore.identity.auth import requires_api_key

        @requires_api_key(provider_name=AGENTCORE_CREDENTIAL_NAME)
        async def _fetch(*, api_key: str) -> str:
            return api_key

        token = asyncio.run(_fetch())
        log.info("Loaded ShipRush token from AgentCore Identity vault")
        return token
    except Exception as e:
        log.info("AgentCore Identity not available (%s), trying env vars", e)
        return None


def _get_token_from_env() -> str | None:
    """Attempt to fetch the ShipRush token from environment variables."""
    env = os.environ.get("SHIPRUSH_ENV", "sandbox").lower()
    token_key = f"SHIPRUSH_SHIPPING_TOKEN_{env.upper()}"
    token = os.environ.get(token_key) or os.environ.get("SHIPRUSH_SHIPPING_TOKEN")
    if token:
        log.info("Loaded ShipRush token from environment variable")
    return token


class ShipRushConfig:
    def __init__(self, shipping_token: str):
        self.env = os.environ.get("SHIPRUSH_ENV", "sandbox").lower()
        self.shipping_token = shipping_token
        self.base_url = os.environ.get(
            "SHIPRUSH_BASE_URL",
            BASE_URLS.get(self.env, BASE_URLS["sandbox"]),
        )


def _build_config() -> ShipRushConfig:
    """Build config: try AgentCore Identity, then env vars."""
    # Try AgentCore Identity vault first (deployed to AgentCore Runtime)
    token = _get_token_from_agentcore()
    if token:
        return ShipRushConfig(shipping_token=token)

    # Fall back to environment variables (local dev or --env flag)
    token = _get_token_from_env()
    if token:
        return ShipRushConfig(shipping_token=token)

    raise RuntimeError(
        "Missing ShipRush API token. Either:\n"
        "  1. Store it in AgentCore Identity vault (see docs/agentcore-deployment-guide.md)\n"
        "  2. Set SHIPRUSH_SHIPPING_TOKEN_PRODUCTION or SHIPRUSH_SHIPPING_TOKEN in .env\n"
        "  3. Pass --env SHIPRUSH_SHIPPING_TOKEN_PRODUCTION=your-token during agentcore deploy"
    )


config = _build_config()
