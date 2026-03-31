import xml.etree.ElementTree as ET

from shiprush.models import (
    Address,
    RateResult,
    ShipmentResult,
    TrackingEvent,
    TrackingResult,
    VoidResult,
)


def _get_text(element: ET.Element, path: str, default: str = "") -> str:
    el = element.find(path)
    return el.text if el is not None and el.text else default


class ShipRushApiError(Exception):
    def __init__(self, messages: list[str]):
        self.messages = messages
        super().__init__("; ".join(messages))


def _check_errors(root: ET.Element) -> None:
    # Check for top-level <Error> response
    if root.tag == "Error":
        msg = _get_text(root, "Message", "Unknown error")
        raise ShipRushApiError([msg])
    # Check for <IsSuccess>false</IsSuccess> with <Messages>
    is_success = _get_text(root, "IsSuccess")
    if is_success == "false":
        errors = []
        for msg_el in root.findall(".//ShippingMessage"):
            severity = _get_text(msg_el, "Severity")
            text = _get_text(msg_el, "Text")
            if severity == "error" and text:
                errors.append(text)
        if errors:
            raise ShipRushApiError(errors)


def parse_rate_response(xml_str: str) -> list[RateResult]:
    root = ET.fromstring(xml_str)
    _check_errors(root)
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
    _check_errors(root)
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
    _check_errors(root)
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
    _check_errors(root)
    # Real API uses <IsSuccess> and <ShipTransaction><Shipment><TrackingNumber>
    shipment = root.find(".//Shipment")
    tracking = _get_text(shipment, "TrackingNumber") if shipment is not None else ""
    is_success = _get_text(root, "IsSuccess", "false").lower() == "true"
    # Also check legacy format
    voided = is_success or _get_text(root, "Voided", "false").lower() == "true"
    return VoidResult(
        tracking_number=tracking or _get_text(root, "TrackingNumber"),
        voided=voided,
        message=_get_text(root, "Message") or None,
    )


