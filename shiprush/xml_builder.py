"""Build ShipRush XML request bodies from Pydantic models."""

import xml.etree.ElementTree as ET

from shiprush.models import Address, Package

# ShipRush uses numeric enum values for carriers, not string names.
# See: https://my.shiprush.com/ShipClassesDocs?typeName=TCarrierType
CARRIER_CODES = {
    "ups": "0",
    "fedex": "1",
    "dhl": "2",
    "usps": "3",
    "endicia": "4",
    "stamps": "5",
    "shiprushusps": "17",
    "17": "17",
}


def _carrier_code(carrier: str) -> str:
    """Map a friendly carrier name to its ShipRush numeric code."""
    return CARRIER_CODES.get(carrier.lower(), carrier)


def _add_address_element(parent: ET.Element, tag: str, address: Address) -> None:
    wrapper = ET.SubElement(parent, tag)
    addr_el = ET.SubElement(wrapper, "Address")
    if address.name:
        ET.SubElement(addr_el, "FirstName").text = address.name
    if address.company:
        ET.SubElement(addr_el, "Company").text = address.company
    ET.SubElement(addr_el, "Address1").text = address.street1
    if address.street2:
        ET.SubElement(addr_el, "Address2").text = address.street2
    ET.SubElement(addr_el, "City").text = address.city
    ET.SubElement(addr_el, "State").text = address.state
    ET.SubElement(addr_el, "PostalCode").text = address.postal_code
    ET.SubElement(addr_el, "Country").text = address.country


def _add_package_element(parent: ET.Element, package: Package) -> None:
    pkg_el = ET.SubElement(parent, "Package")
    ET.SubElement(pkg_el, "PackageActualWeight").text = str(package.weight_lb)
    # ShipRush expects integer dimensions
    if package.length_in is not None:
        ET.SubElement(pkg_el, "Length").text = str(round(package.length_in))
    if package.width_in is not None:
        ET.SubElement(pkg_el, "Width").text = str(round(package.width_in))
    if package.height_in is not None:
        ET.SubElement(pkg_el, "Height").text = str(round(package.height_in))


def build_rate_request(
    origin: Address,
    destination: Address,
    packages: list[Package],
    carrier_filter: str | None = None,
) -> str:
    """Build XML for the /shipment/rateshopping endpoint."""
    root = ET.Element("RateShoppingRequest")
    ship_tx = ET.SubElement(root, "ShipTransaction")
    shipment = ET.SubElement(ship_tx, "Shipment")
    if carrier_filter:
        ET.SubElement(shipment, "Carrier").text = _carrier_code(carrier_filter)
    for pkg in packages:
        _add_package_element(shipment, pkg)
    _add_address_element(shipment, "ShipperAddress", origin)
    _add_address_element(shipment, "DeliveryAddress", destination)
    return ET.tostring(root, encoding="unicode", xml_declaration=False)


def build_ship_request(
    origin: Address,
    destination: Address,
    packages: list[Package],
    quote_id: str,
    reference: str | None = None,
    carrier: str | None = None,
    service_code: str | None = None,
    shipping_account_id: str | None = None,
) -> str:
    """Build XML for the /shipment/ship endpoint using a rate shopping quote."""
    root = ET.Element("ShipRequest")
    ship_tx = ET.SubElement(root, "ShipTransaction")
    if reference:
        order = ET.SubElement(ship_tx, "Order")
        ET.SubElement(order, "OrderNumber").text = reference
    shipment = ET.SubElement(ship_tx, "Shipment")
    ET.SubElement(shipment, "ShipmentQuoteId").text = quote_id
    ET.SubElement(shipment, "ShipViaQuoteId").text = "true"
    if carrier:
        ET.SubElement(shipment, "Carrier").text = _carrier_code(carrier)
    if service_code:
        # ShipRush uses "UPSServiceType" as the element name for ALL carriers,
        # not just UPS. This is a ShipRush API naming quirk.
        ET.SubElement(shipment, "UPSServiceType").text = service_code
    if shipping_account_id:
        ET.SubElement(shipment, "ShippingAccountId").text = shipping_account_id
    for pkg in packages:
        _add_package_element(shipment, pkg)
    _add_address_element(shipment, "ShipperAddress", origin)
    _add_address_element(shipment, "DeliveryAddress", destination)
    return ET.tostring(root, encoding="unicode", xml_declaration=False)


def build_tracking_request(shipment_id: str) -> str:
    """Build XML for the /shipment/tracking endpoint."""
    root = ET.Element("TrackingRequest")
    ET.SubElement(root, "ShipmentId").text = shipment_id
    return ET.tostring(root, encoding="unicode", xml_declaration=False)


def build_void_request(shipment_id: str) -> str:
    """Build XML for the /shipment/void endpoint."""
    root = ET.Element("VoidRequest")
    ship_tx = ET.SubElement(root, "ShipTransaction")
    shipment = ET.SubElement(ship_tx, "Shipment")
    ET.SubElement(shipment, "ShipmentId").text = shipment_id
    return ET.tostring(root, encoding="unicode", xml_declaration=False)
