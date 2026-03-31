from pathlib import Path

from shiprush.xml_parser import parse_rate_response, parse_ship_response, parse_track_response, parse_void_response

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_rate_response():
    xml_str = (FIXTURES / "rate_response.xml").read_text()
    rates = parse_rate_response(xml_str)
    assert len(rates) == 2
    assert rates[0].carrier == "SR36232408"
    assert rates[0].service_name == "USPS Ground Advantage"
    assert rates[0].service_code == "USPSGNDADV"
    assert rates[0].rate_amount == 12.27
    assert rates[0].currency == "USD"
    assert rates[0].transit_days == 4
    assert rates[0].quote_id == "rate_abc123"
    assert rates[1].service_name == "USPS Priority"
    assert rates[1].rate_amount == 16.99


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
