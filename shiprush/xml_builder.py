import xml.etree.ElementTree as ET

from shiprush.models import Address, Package

CARRIER_CODES = {
    "ups": "0",
    "fedex": "1",
    "dhl": "2",
    "usps": "3",
    "endicia": "4",
    "stamps": "5",
}


def _carrier_code(carrier: str) -> str:
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
    if package.length_in is not None:
        ET.SubElement(pkg_el, "Length").text = str(int(package.length_in))
    if package.width_in is not None:
        ET.SubElement(pkg_el, "Width").text = str(int(package.width_in))
    if package.height_in is not None:
        ET.SubElement(pkg_el, "Height").text = str(int(package.height_in))


def build_rate_request(
    origin: Address,
    destination: Address,
    packages: list[Package],
    carrier_filter: str | None = None,
) -> str:
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
    carrier: str,
    service_name: str,
    reference: str | None = None,
) -> str:
    root = ET.Element("ShipRequest")
    ship_tx = ET.SubElement(root, "ShipTransaction")
    if reference:
        order = ET.SubElement(ship_tx, "Order")
        ET.SubElement(order, "OrderNumber").text = reference
    shipment = ET.SubElement(ship_tx, "Shipment")
    ET.SubElement(shipment, "Carrier").text = _carrier_code(carrier)
    ET.SubElement(shipment, "UPSServiceType").text = service_name
    for pkg in packages:
        _add_package_element(shipment, pkg)
    _add_address_element(shipment, "ShipperAddress", origin)
    _add_address_element(shipment, "DeliveryAddress", destination)
    return ET.tostring(root, encoding="unicode", xml_declaration=False)


def build_tracking_request(tracking_number: str) -> str:
    root = ET.Element("TrackingRequest")
    ship_tx = ET.SubElement(root, "ShipTransaction")
    shipment = ET.SubElement(ship_tx, "Shipment")
    ET.SubElement(shipment, "TrackingNumber").text = tracking_number
    return ET.tostring(root, encoding="unicode", xml_declaration=False)


def build_void_request(tracking_number: str, carrier: str | None = None) -> str:
    root = ET.Element("VoidRequest")
    ship_tx = ET.SubElement(root, "ShipTransaction")
    shipment = ET.SubElement(ship_tx, "Shipment")
    ET.SubElement(shipment, "TrackingNumber").text = tracking_number
    if carrier:
        ET.SubElement(shipment, "Carrier").text = _carrier_code(carrier)
    return ET.tostring(root, encoding="unicode", xml_declaration=False)


