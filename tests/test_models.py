from shiprush.models import Address, Package, RateResult, ShipmentResult, TrackingEvent, TrackingResult, VoidResult


def test_address_required_fields():
    addr = Address(street1="123 Main St", city="Seattle", state="WA", postal_code="98101", country="US")
    assert addr.street1 == "123 Main St"
    assert addr.name is None
    assert addr.company is None
    assert addr.street2 is None


def test_address_all_fields():
    addr = Address(
        name="John Doe",
        company="Acme Inc",
        street1="123 Main St",
        street2="Suite 100",
        city="Seattle",
        state="WA",
        postal_code="98101",
        country="US",
    )
    assert addr.company == "Acme Inc"
    assert addr.street2 == "Suite 100"


def test_package_required_fields():
    pkg = Package(weight_lb=2.5)
    assert pkg.weight_lb == 2.5
    assert pkg.length_in is None


def test_package_all_fields():
    pkg = Package(weight_lb=5.0, length_in=12.0, width_in=8.0, height_in=6.0)
    assert pkg.length_in == 12.0


def test_rate_result():
    rate = RateResult(
        carrier="FedEx",
        service_name="FedEx Ground",
        rate_amount=12.50,
        currency="USD",
        estimated_delivery_date="2026-04-03",
    )
    assert rate.rate_amount == 12.50


def test_shipment_result():
    result = ShipmentResult(
        shipment_id="448ecd71-test",
        tracking_number="794644790132",
        carrier="fedex",
        service_name="FedEx Ground",
        total_cost=12.50,
        currency="USD",
    )
    assert result.shipment_id == "448ecd71-test"
    assert result.tracking_number == "794644790132"
    assert result.label_url is None


def test_tracking_result():
    event = TrackingEvent(
        timestamp="2026-03-30T14:22:00Z",
        location="Memphis, TN",
        description="Departed FedEx facility",
    )
    result = TrackingResult(
        shipment_id="448ecd71-test",
        tracking_number="794644790132",
        carrier="fedex",
        status="In Transit",
        events=[event],
    )
    assert len(result.events) == 1
    assert result.estimated_delivery is None


def test_void_result():
    result = VoidResult(shipment_id="448ecd71-test", voided=True)
    assert result.message is None


