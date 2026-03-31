from pathlib import Path

from shiprush.xml_parser import parse_rate_response, parse_ship_response, parse_track_response, parse_void_response, parse_address_validate_response

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_rate_response():
    xml_str = (FIXTURES / "rate_response.xml").read_text()
    rates = parse_rate_response(xml_str)
    assert len(rates) == 2
    assert rates[0].carrier == "FedEx"
    assert rates[0].service_name == "FedEx Ground"
    assert rates[0].rate_amount == 12.50
    assert rates[0].currency == "USD"
    assert rates[0].estimated_delivery_date == "2026-04-03"
    assert rates[1].carrier == "UPS"
    assert rates[1].rate_amount == 11.75


def test_parse_ship_response():
    xml_str = (FIXTURES / "ship_response.xml").read_text()
    result = parse_ship_response(xml_str)
    assert result.tracking_number == "794644790132"
    assert result.carrier == "FedEx"
    assert result.service_name == "FedEx Ground"
    assert result.total_cost == 12.50
    assert result.label_url == "https://labels.shiprush.com/abc123.pdf"


def test_parse_track_response():
    xml_str = (FIXTURES / "track_response.xml").read_text()
    result = parse_track_response(xml_str)
    assert result.tracking_number == "794644790132"
    assert result.status == "In Transit"
    assert result.estimated_delivery == "2026-04-03"
    assert len(result.events) == 2
    assert result.events[0].location == "Memphis, TN"


def test_parse_void_response():
    xml_str = (FIXTURES / "void_response.xml").read_text()
    result = parse_void_response(xml_str)
    assert result.tracking_number == "794644790132"
    assert result.voided is True
    assert result.message is None


def test_parse_address_validate_response():
    xml_str = (FIXTURES / "address_validate_response.xml").read_text()
    result = parse_address_validate_response(xml_str)
    assert result.valid is True
    assert result.corrected_address is not None
    assert result.corrected_address.street1 == "123 MAIN ST"
    assert result.corrected_address.postal_code == "98101-1234"
