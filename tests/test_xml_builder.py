import xml.etree.ElementTree as ET

from shiprush.models import Address, Package
from shiprush.xml_builder import build_rate_request, build_ship_request, build_void_request


ORIGIN = Address(
    name="John Sender",
    company="Acme Corp",
    street1="100 Main St",
    city="Seattle",
    state="WA",
    postal_code="98101",
    country="US",
)

DESTINATION = Address(
    name="Jane Receiver",
    street1="200 Oak Ave",
    city="Portland",
    state="OR",
    postal_code="97201",
    country="US",
)

PACKAGES = [Package(weight_lb=2.5, length_in=10, width_in=8, height_in=4)]


def test_build_rate_request_structure():
    xml_str = build_rate_request(ORIGIN, DESTINATION, PACKAGES)
    root = ET.fromstring(xml_str)
    assert root.tag == "RateShoppingRequest"
    ship_tx = root.find("ShipTransaction")
    assert ship_tx is not None
    shipment = ship_tx.find("Shipment")
    assert shipment is not None


def test_build_rate_request_addresses():
    xml_str = build_rate_request(ORIGIN, DESTINATION, PACKAGES)
    root = ET.fromstring(xml_str)
    shipment = root.find("ShipTransaction/Shipment")
    delivery_addr = shipment.find("DeliveryAddress/Address")
    assert delivery_addr.find("FirstName").text == "Jane Receiver"
    assert delivery_addr.find("City").text == "Portland"
    shipper_addr = shipment.find("ShipperAddress/Address")
    assert shipper_addr.find("FirstName").text == "John Sender"
    assert shipper_addr.find("Company").text == "Acme Corp"


def test_build_rate_request_package():
    xml_str = build_rate_request(ORIGIN, DESTINATION, PACKAGES)
    root = ET.fromstring(xml_str)
    package = root.find("ShipTransaction/Shipment/Package")
    assert package.find("PackageActualWeight").text == "2.5"
    assert package.find("Length").text == "10"
    assert package.find("Width").text == "8"
    assert package.find("Height").text == "4"


def test_build_rate_request_carrier_filter():
    xml_str = build_rate_request(ORIGIN, DESTINATION, PACKAGES, carrier_filter="FedEx")
    root = ET.fromstring(xml_str)
    carrier = root.find("ShipTransaction/Shipment/Carrier")
    assert carrier.text == "1"  # FedEx maps to carrier code 1


def test_build_rate_request_no_carrier_filter():
    xml_str = build_rate_request(ORIGIN, DESTINATION, PACKAGES)
    root = ET.fromstring(xml_str)
    carrier = root.find("ShipTransaction/Shipment/Carrier")
    assert carrier is None or carrier.text is None or carrier.text == ""


def test_build_ship_request():
    xml_str = build_ship_request(
        ORIGIN, DESTINATION, PACKAGES,
        quote_id="rate_abc123", reference="ORDER-123",
    )
    root = ET.fromstring(xml_str)
    assert root.tag == "ShipRequest"
    shipment = root.find("ShipTransaction/Shipment")
    assert shipment.find("ShipmentQuoteId").text == "rate_abc123"
    assert shipment.find("ShipViaQuoteId").text == "true"
    order = root.find("ShipTransaction/Order")
    assert order.find("OrderNumber").text == "ORDER-123"


def test_build_void_request():
    xml_str = build_void_request("448ecd71-76ae-4b98-9118-b41e0028f855")
    root = ET.fromstring(xml_str)
    assert root.tag == "VoidRequest"
    shipment = root.find("ShipTransaction/Shipment")
    assert shipment.find("ShipmentId").text == "448ecd71-76ae-4b98-9118-b41e0028f855"


