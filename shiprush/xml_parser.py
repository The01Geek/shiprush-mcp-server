import xml.etree.ElementTree as ET

from shiprush.models import (
    Address,
    AddressValidationResult,
    RateResult,
    ShipmentResult,
    TrackingEvent,
    TrackingResult,
    VoidResult,
)


def _get_text(element: ET.Element, path: str, default: str = "") -> str:
    el = element.find(path)
    return el.text if el is not None and el.text else default


def parse_rate_response(xml_str: str) -> list[RateResult]:
    root = ET.fromstring(xml_str)
    rates = []
    for rate_el in root.findall(".//Rate"):
        rates.append(RateResult(
            carrier=_get_text(rate_el, "Carrier"),
            service_name=_get_text(rate_el, "ServiceDescription"),
            rate_amount=float(_get_text(rate_el, "TotalCharges", "0")),
            currency=_get_text(rate_el, "Currency", "USD"),
            estimated_delivery_date=_get_text(rate_el, "EstimatedDeliveryDate") or None,
        ))
    return rates


def parse_ship_response(xml_str: str) -> ShipmentResult:
    root = ET.fromstring(xml_str)
    shipment = root.find(".//Shipment")
    return ShipmentResult(
        tracking_number=_get_text(shipment, "TrackingNumber"),
        carrier=_get_text(shipment, "Carrier"),
        service_name=_get_text(shipment, "ServiceDescription"),
        label_url=_get_text(shipment, "LabelUrl") or None,
        total_cost=float(_get_text(shipment, "ShippingCharges", "0")),
        currency=_get_text(shipment, "Currency", "USD"),
    )


def parse_track_response(xml_str: str) -> TrackingResult:
    root = ET.fromstring(xml_str)
    shipment = root.find(".//Shipment")
    events = []
    for event_el in root.findall(".//Event"):
        events.append(TrackingEvent(
            timestamp=_get_text(event_el, "Timestamp"),
            location=_get_text(event_el, "Location"),
            description=_get_text(event_el, "Description"),
        ))
    return TrackingResult(
        tracking_number=_get_text(shipment, "TrackingNumber"),
        carrier=_get_text(shipment, "Carrier"),
        status=_get_text(shipment, "Status"),
        estimated_delivery=_get_text(shipment, "EstimatedDelivery") or None,
        events=events,
    )


def parse_void_response(xml_str: str) -> VoidResult:
    root = ET.fromstring(xml_str)
    return VoidResult(
        tracking_number=_get_text(root, "TrackingNumber"),
        voided=_get_text(root, "Voided", "false").lower() == "true",
        message=_get_text(root, "Message") or None,
    )


def parse_address_validate_response(xml_str: str) -> AddressValidationResult:
    root = ET.fromstring(xml_str)
    valid = _get_text(root, "Valid", "false").lower() == "true"
    corrected = None
    addr_el = root.find(".//CorrectedAddress/Address")
    if addr_el is not None:
        corrected = Address(
            name=_get_text(addr_el, "FirstName") or None,
            company=_get_text(addr_el, "Company") or None,
            street1=_get_text(addr_el, "Address1"),
            street2=_get_text(addr_el, "Address2") or None,
            city=_get_text(addr_el, "City"),
            state=_get_text(addr_el, "State"),
            postal_code=_get_text(addr_el, "PostalCode"),
            country=_get_text(addr_el, "Country"),
        )
    return AddressValidationResult(valid=valid, corrected_address=corrected)
