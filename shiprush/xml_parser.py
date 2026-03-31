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
    # RateShopping response uses AvailableService elements
    for svc in root.findall(".//AvailableService"):
        rates.append(RateResult(
            carrier=_get_text(svc, "ShippingAccountNumber") or _get_text(svc, "Carrier"),
            service_name=_get_text(svc, "Name"),
            service_code=_get_text(svc, "ServiceType"),
            rate_amount=float(_get_text(svc, "Total", "0")),
            currency=_get_text(svc, "Currency", "USD"),
            estimated_delivery_date=_get_text(svc, "ExpectedDelivery") or None,
            transit_days=int(_get_text(svc, "TimeInTransitBusinessDays", "0")) or None,
            quote_id=_get_text(svc, "ShipmentQuoteId") or None,
            shipping_account_id=_get_text(svc, "ShippingAccountId") or None,
        ))
    return rates


def parse_ship_response(xml_str: str) -> ShipmentResult:
    root = ET.fromstring(xml_str)
    _check_errors(root)
    shipment = root.find(".//Shipment")
    return ShipmentResult(
        shipment_id=_get_text(shipment, "ShipmentId"),
        tracking_number=_get_text(shipment, "TrackingNumber"),
        carrier=_get_text(shipment, "Carrier"),
        service_name=_get_text(shipment, "ServiceDescription") or _get_text(shipment, "UPSServiceType"),
        label_url=_get_text(shipment, "LabelUrl") or None,
        total_cost=float(_get_text(shipment, "ShippingCharges", "0")),
        currency=_get_text(shipment, "CurrencyCode", "USD"),
    )


def parse_track_response(xml_str: str) -> TrackingResult:
    root = ET.fromstring(xml_str)
    _check_errors(root)
    # TrackingResponse has ShipmentId at root and TrackingInfo child
    shipment_id = _get_text(root, "ShipmentId")
    tracking_info = root.find(".//TrackingInfo")
    # Fall back to .//Shipment for legacy format
    source = tracking_info if tracking_info is not None else root.find(".//Shipment")
    events = []
    for event_el in root.findall(".//Event"):
        events.append(TrackingEvent(
            timestamp=_get_text(event_el, "Timestamp"),
            location=_get_text(event_el, "Location"),
            description=_get_text(event_el, "Description"),
        ))
    return TrackingResult(
        shipment_id=shipment_id,
        tracking_number=_get_text(source, "TrackingNumber") if source is not None else "",
        carrier=_get_text(source, "Carrier") if source is not None else "",
        status=_get_text(source, "Status") if source is not None else "",
        estimated_delivery=(_get_text(source, "EstimatedDelivery") if source is not None else "") or None,
        events=events,
    )


def parse_void_response(xml_str: str) -> VoidResult:
    root = ET.fromstring(xml_str)
    _check_errors(root)
    shipment = root.find(".//Shipment")
    shipment_id = _get_text(shipment, "ShipmentId") if shipment is not None else ""
    is_success = _get_text(root, "IsSuccess", "false").lower() == "true"
    return VoidResult(
        shipment_id=shipment_id,
        voided=is_success,
        message=_get_text(root, "Message") or None,
    )


