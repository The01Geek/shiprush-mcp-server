import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from shiprush.client import ShipRushClient
from shiprush.models import Address, Package


ORIGIN = Address(street1="100 Main St", city="Seattle", state="WA", postal_code="98101", country="US")
DEST = Address(street1="200 Oak Ave", city="Portland", state="OR", postal_code="97201", country="US")
PACKAGES = [Package(weight_lb=2.5)]

# Sample XML responses for mocking HTTP calls
RATE_XML = """<RateResponse><ShipTransaction><Shipment><RateDetails>
<Rate><Carrier>FedEx</Carrier><ServiceType>FedExGround</ServiceType>
<ServiceDescription>FedEx Ground</ServiceDescription><TotalCharges>12.50</TotalCharges>
<Currency>USD</Currency></Rate></RateDetails></Shipment></ShipTransaction></RateResponse>"""

SHIP_XML = """<ShipResponse><ShipTransaction><Shipment>
<TrackingNumber>794644790132</TrackingNumber><Carrier>FedEx</Carrier>
<ServiceType>FedExGround</ServiceType><ServiceDescription>FedEx Ground</ServiceDescription>
<ShippingCharges>12.50</ShippingCharges><Currency>USD</Currency>
</Shipment></ShipTransaction></ShipResponse>"""

TRACK_XML = """<TrackResponse><ShipTransaction><Shipment>
<TrackingNumber>794644790132</TrackingNumber><Carrier>FedEx</Carrier>
<Status>Delivered</Status><TrackingEvents><Event>
<Timestamp>2026-03-30T14:00:00Z</Timestamp><Location>Portland, OR</Location>
<Description>Delivered</Description></Event></TrackingEvents>
</Shipment></ShipTransaction></TrackResponse>"""

VOID_XML = """<VoidResponse><Messages /><IsSuccess>true</IsSuccess>
<ShipTransaction><Shipment><TrackingNumber>794644790132</TrackingNumber>
</Shipment></ShipTransaction></VoidResponse>"""



def _mock_response(text: str, status_code: int = 200):
    resp = AsyncMock()
    resp.text = text
    resp.status_code = status_code
    resp.raise_for_status = lambda: None
    return resp


@pytest.mark.asyncio
async def test_get_rates():
    client = ShipRushClient(token="test-token", base_url="https://sandbox.api.my.shiprush.com")
    with patch.object(client._http, "post", return_value=_mock_response(RATE_XML)) as mock_post:
        rates = await client.get_rates(ORIGIN, DEST, PACKAGES)
        assert len(rates) == 1
        assert rates[0].carrier == "FedEx"
        assert rates[0].rate_amount == 12.50
        mock_post.assert_called_once()


@pytest.mark.asyncio
async def test_create_shipment():
    client = ShipRushClient(token="test-token", base_url="https://sandbox.api.my.shiprush.com")
    with patch.object(client._http, "post", return_value=_mock_response(SHIP_XML)) as mock_post:
        result = await client.create_shipment(ORIGIN, DEST, PACKAGES, "FedEx", "FedExGround")
        assert result.tracking_number == "794644790132"
        mock_post.assert_called_once()


@pytest.mark.asyncio
async def test_track_shipment():
    client = ShipRushClient(token="test-token", base_url="https://sandbox.api.my.shiprush.com")
    with patch.object(client._http, "post", return_value=_mock_response(TRACK_XML)):
        result = await client.track_shipment("794644790132")
        assert result.status == "Delivered"


@pytest.mark.asyncio
async def test_void_shipment():
    client = ShipRushClient(token="test-token", base_url="https://sandbox.api.my.shiprush.com")
    with patch.object(client._http, "post", return_value=_mock_response(VOID_XML)):
        result = await client.void_shipment("794644790132")
        assert result.voided is True



@pytest.mark.asyncio
async def test_client_sends_auth_header():
    client = ShipRushClient(token="my-secret-token", base_url="https://sandbox.api.my.shiprush.com")
    with patch.object(client._http, "post", return_value=_mock_response(RATE_XML)) as mock_post:
        await client.get_rates(ORIGIN, DEST, PACKAGES)
        call_kwargs = mock_post.call_args
        headers = call_kwargs.kwargs.get("headers", {})
        assert headers["X-SHIPRUSH-SHIPPING-TOKEN"] == "my-secret-token"


@pytest.mark.asyncio
async def test_client_http_500_raises():
    client = ShipRushClient(token="test-token", base_url="https://sandbox.api.my.shiprush.com")
    error_resp = AsyncMock()
    error_resp.status_code = 500
    error_resp.text = "Internal Server Error"
    error_resp.raise_for_status = MagicMock(side_effect=Exception("HTTP 500"))
    with patch.object(client._http, "post", return_value=error_resp):
        with pytest.raises(Exception, match="HTTP 500"):
            await client.get_rates(ORIGIN, DEST, PACKAGES)
