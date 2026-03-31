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
        self.shipping_token = os.environ.get(token_key) or os.environ["SHIPRUSH_SHIPPING_TOKEN"]
        self.base_url = os.environ.get("SHIPRUSH_BASE_URL", BASE_URLS.get(self.env, BASE_URLS["sandbox"]))

    @property
    def rate_url(self) -> str:
        return f"{self.base_url}/shipmentservice.svc/shipment/rate"

    @property
    def ship_url(self) -> str:
        return f"{self.base_url}/shipmentservice.svc/shipment/ship"

    @property
    def track_url(self) -> str:
        return f"{self.base_url}/shipmentservice.svc/shipment/track"

    @property
    def void_url(self) -> str:
        return f"{self.base_url}/shipmentservice.svc/shipment/void"

    @property
    def address_validate_url(self) -> str:
        return f"{self.base_url}/shipmentservice.svc/address/validate"

    @property
    def headers(self) -> dict[str, str]:
        return {
            "X-SHIPRUSH-SHIPPING-TOKEN": self.shipping_token,
            "Content-Type": "application/xml",
        }


config = ShipRushConfig()
