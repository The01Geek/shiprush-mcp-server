"""ShipRush API configuration loaded from environment variables."""

import os

from dotenv import load_dotenv

load_dotenv()

BASE_URLS = {
    "sandbox": "https://sandbox.api.my.shiprush.com",
    "production": "https://api.my.shiprush.com",
}


class ShipRushConfig:
    def __init__(self):
        self.env = os.environ.get("SHIPRUSH_ENV", "sandbox").lower()
        token_key = f"SHIPRUSH_SHIPPING_TOKEN_{self.env.upper()}"
        self.shipping_token = os.environ.get(token_key) or os.environ.get("SHIPRUSH_SHIPPING_TOKEN")
        if not self.shipping_token:
            raise RuntimeError(
                f"Missing ShipRush API token. Set {token_key} or SHIPRUSH_SHIPPING_TOKEN in .env"
            )
        self.base_url = os.environ.get(
            "SHIPRUSH_BASE_URL",
            BASE_URLS.get(self.env, BASE_URLS["sandbox"]),
        )


config = ShipRushConfig()
