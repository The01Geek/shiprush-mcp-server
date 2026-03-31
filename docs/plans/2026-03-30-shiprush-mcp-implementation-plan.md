# ShipRush MCP Server Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a Python FastMCP server exposing 5 ShipRush shipping tools, deployable to AWS AgentCore Runtime.

**Architecture:** Stateless FastMCP server on `0.0.0.0:8000/mcp` wrapping ShipRush's XML REST API with an async httpx client. Pydantic models define tool schemas (inlined, no `$ref`). XML serialization is isolated in dedicated modules. Deployed as ARM64 container via `agentcore configure` + `agentcore launch`.

**Tech Stack:** Python 3.11+, FastMCP (`mcp` package), httpx, Pydantic v2, pytest, bedrock-agentcore-starter-toolkit

**Design Doc:** `docs/plans/2026-03-30-shiprush-mcp-server-design.md`

---

## ShipRush API Reference (for implementer)

### Endpoints
- **Rate:** `POST /shipmentservice.svc/shipment/rate`
- **Ship:** `POST /shipmentservice.svc/shipment/ship`
- **Track:** `POST /shipmentservice.svc/shipment/track` (or via tracking API)
- **Void:** `POST /shipmentservice.svc/shipment/void`
- **Address Validation:** `POST /shipmentservice.svc/address/validate`

### Authentication Headers
```
X-SHIPRUSH-SHIPPING-TOKEN: {token}
Content-Type: application/xml
```

### XML Request Structure
ShipRush uses a `<Request><ShipTransaction><Shipment>` XML envelope. Key elements:
- `<Carrier>` — enum string: `UPS`, `FedEx`, `USPS`, etc.
- `<ServiceType>` (TUPSService) — e.g., `UPSGround`, `FedExGround`, `USPSPriority`
- `<Package>` — contains `<PackageActualWeight>`, `<PackagingType>`, dimensions
- `<DeliveryAddress><Address>` — `FirstName`, `Company`, `Address1`, `Address2`, `City`, `State`, `PostalCode`, `Country`, `Phone`
- `<ShipperAddress><Address>` — same structure as DeliveryAddress

### Carrier Codes (TCarrierType)
`UPS`, `FedEx`, `USPS`, `DHL`, `Endicia`, `Stamps`, `OnTrac`, `CanadaPost`, + 50 more

### Service Codes (TUPSService) — key ones
- UPS: `UPSGround`, `UPSNextDayAir`, `UPS2ndDayAir`, `UPS3DaySelect`
- FedEx: `FedExGround`, `FedExHomeDelivery`, `FedEx2Day`, `FedExFirstOvernight`
- USPS: `USPSPriority`, `USPSFirstClass`, `USPSExpress`, `USPSGroundAdvantage`

### Response Format
XML response with `<ShipTransaction>` containing results. HTTP 200 = processed (check inner status). HTTP 500 = structural/auth error.

---

## Task 1: Project Scaffolding & Configuration

**Files:**
- Create: `requirements.txt`
- Create: `config.py`
- Create: `shiprush/__init__.py`
- Create: `__init__.py`
- Create: `tests/__init__.py`
- Create: `.gitignore`

**Step 1: Initialize git repo**

```bash
cd "C:/Projects/a,Playground/ShipRush-MCP"
git init
```

**Step 2: Create `.gitignore`**

```
__pycache__/
*.pyc
.env
.venv/
venv/
*.egg-info/
dist/
build/
.bedrock_agentcore/
.bedrock_agentcore.yaml
.pytest_cache/
```

**Step 3: Create `requirements.txt`**

```
mcp>=1.0
httpx>=0.27
pydantic>=2.0
pytest>=8.0
pytest-asyncio>=0.24
bedrock-agentcore-starter-toolkit
```

**Step 4: Create `config.py`**

```python
import os


class ShipRushConfig:
    def __init__(self):
        self.shipping_token = os.environ["SHIPRUSH_SHIPPING_TOKEN"]
        self.base_url = os.environ.get(
            "SHIPRUSH_BASE_URL",
            "https://sandbox.api.my.shiprush.com",
        )

    @property
    def rate_url(self) -> str:
        return f"{self.base_url}/shipmentservice.svc/shipment/rate"

    @property
    def ship_url(self) -> str:
        return f"{self.base_url}/shipmentservice.svc/shipment/ship"

    @property
    def track_url(self) -> str:
        return f"{self.base_url}/shipmentservice.svc/shipment/track"

    @property
    def void_url(self) -> str:
        return f"{self.base_url}/shipmentservice.svc/shipment/void"

    @property
    def address_validate_url(self) -> str:
        return f"{self.base_url}/shipmentservice.svc/address/validate"

    @property
    def headers(self) -> dict[str, str]:
        return {
            "X-SHIPRUSH-SHIPPING-TOKEN": self.shipping_token,
            "Content-Type": "application/xml",
        }


config = ShipRushConfig()
```

**Step 5: Create package init files**

`__init__.py` — empty
`shiprush/__init__.py` — empty
`tests/__init__.py` — empty

**Step 6: Install dependencies**

```bash
pip install -r requirements.txt
```

**Step 7: Commit**

```bash
git add .gitignore requirements.txt config.py __init__.py shiprush/__init__.py tests/__init__.py
git commit -m "feat: project scaffolding with config and dependencies"
```

---

## Task 2: Pydantic Models

**Files:**
- Create: `shiprush/models.py`
- Create: `tests/test_models.py`

**Step 1: Write the failing test**

Create `tests/test_models.py`:

```python
from shiprush.models import Address, Package, RateResult, ShipmentResult, TrackingEvent, TrackingResult, VoidResult, AddressValidationResult


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
        tracking_number="794644790132",
        carrier="fedex",
        service_name="FedEx Ground",
        total_cost=12.50,
        currency="USD",
    )
    assert result.tracking_number == "794644790132"
    assert result.label_url is None


def test_tracking_result():
    event = TrackingEvent(
        timestamp="2026-03-30T14:22:00Z",
        location="Memphis, TN",
        description="Departed FedEx facility",
    )
    result = TrackingResult(
        tracking_number="794644790132",
        carrier="fedex",
        status="In Transit",
        events=[event],
    )
    assert len(result.events) == 1
    assert result.estimated_delivery is None


def test_void_result():
    result = VoidResult(tracking_number="794644790132", voided=True)
    assert result.message is None


def test_address_validation_result():
    result = AddressValidationResult(valid=True)
    assert result.corrected_address is None
    assert result.suggestions == []
    assert result.errors == []
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_models.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'shiprush.models'`

**Step 3: Write the implementation**

Create `shiprush/models.py`:

```python
from pydantic import BaseModel


class Address(BaseModel):
    name: str | None = None
    company: str | None = None
    street1: str
    street2: str | None = None
    city: str
    state: str
    postal_code: str
    country: str


class Package(BaseModel):
    weight_lb: float
    length_in: float | None = None
    width_in: float | None = None
    height_in: float | None = None


class RateResult(BaseModel):
    carrier: str
    service_name: str
    rate_amount: float
    currency: str
    estimated_delivery_date: str | None = None


class ShipmentResult(BaseModel):
    tracking_number: str
    carrier: str
    service_name: str
    label_url: str | None = None
    total_cost: float
    currency: str


class TrackingEvent(BaseModel):
    timestamp: str
    location: str
    description: str


class TrackingResult(BaseModel):
    tracking_number: str
    carrier: str
    status: str
    estimated_delivery: str | None = None
    events: list[TrackingEvent]


class VoidResult(BaseModel):
    tracking_number: str
    voided: bool
    message: str | None = None


class AddressValidationResult(BaseModel):
    valid: bool
    corrected_address: Address | None = None
    suggestions: list[str] = []
    errors: list[str] = []
```

**Step 4: Run test to verify it passes**

```bash
pytest tests/test_models.py -v
```

Expected: All 8 tests PASS

**Step 5: Commit**

```bash
git add shiprush/models.py tests/test_models.py
git commit -m "feat: add Pydantic models for all tool inputs and outputs"
```

---

## Task 3: XML Builder

**Files:**
- Create: `shiprush/xml_builder.py`
- Create: `tests/test_xml_builder.py`

**Step 1: Write the failing test**

Create `tests/test_xml_builder.py`:

```python
import xml.etree.ElementTree as ET

from shiprush.models import Address, Package
from shiprush.xml_builder import build_rate_request, build_ship_request, build_void_request, build_address_validate_request


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
    assert root.tag == "RateRequest"
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
    assert carrier.text == "FedEx"


def test_build_rate_request_no_carrier_filter():
    xml_str = build_rate_request(ORIGIN, DESTINATION, PACKAGES)
    root = ET.fromstring(xml_str)
    carrier = root.find("ShipTransaction/Shipment/Carrier")
    assert carrier is None or carrier.text is None or carrier.text == ""


def test_build_ship_request():
    xml_str = build_ship_request(
        ORIGIN, DESTINATION, PACKAGES,
        carrier="UPS", service_name="UPSGround", reference="ORDER-123",
    )
    root = ET.fromstring(xml_str)
    assert root.tag == "ShipRequest"
    shipment = root.find("ShipTransaction/Shipment")
    assert shipment.find("Carrier").text == "UPS"
    assert shipment.find("ServiceType").text == "UPSGround"
    order = root.find("ShipTransaction/Order")
    assert order.find("OrderNumber").text == "ORDER-123"


def test_build_void_request():
    xml_str = build_void_request("794644790132", carrier="FedEx")
    root = ET.fromstring(xml_str)
    assert root.tag == "VoidRequest"
    assert root.find("TrackingNumber").text == "794644790132"
    assert root.find("Carrier").text == "FedEx"


def test_build_address_validate_request():
    addr = Address(street1="123 Main St", city="Seattle", state="WA", postal_code="98101", country="US")
    xml_str = build_address_validate_request(addr)
    root = ET.fromstring(xml_str)
    assert root.tag == "AddressValidateRequest"
    address = root.find("Address")
    assert address.find("Address1").text == "123 Main St"
    assert address.find("City").text == "Seattle"
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_xml_builder.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'shiprush.xml_builder'`

**Step 3: Write the implementation**

Create `shiprush/xml_builder.py`:

```python
import xml.etree.ElementTree as ET

from shiprush.models import Address, Package


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
    root = ET.Element("RateRequest")
    ship_tx = ET.SubElement(root, "ShipTransaction")
    shipment = ET.SubElement(ship_tx, "Shipment")
    if carrier_filter:
        ET.SubElement(shipment, "Carrier").text = carrier_filter
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
    ET.SubElement(shipment, "Carrier").text = carrier
    ET.SubElement(shipment, "ServiceType").text = service_name
    for pkg in packages:
        _add_package_element(shipment, pkg)
    _add_address_element(shipment, "ShipperAddress", origin)
    _add_address_element(shipment, "DeliveryAddress", destination)
    return ET.tostring(root, encoding="unicode", xml_declaration=False)


def build_void_request(tracking_number: str, carrier: str | None = None) -> str:
    root = ET.Element("VoidRequest")
    ET.SubElement(root, "TrackingNumber").text = tracking_number
    if carrier:
        ET.SubElement(root, "Carrier").text = carrier
    return ET.tostring(root, encoding="unicode", xml_declaration=False)


def build_address_validate_request(address: Address) -> str:
    root = ET.Element("AddressValidateRequest")
    addr_el = ET.SubElement(root, "Address")
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
    return ET.tostring(root, encoding="unicode", xml_declaration=False)
```

**Step 4: Run test to verify it passes**

```bash
pytest tests/test_xml_builder.py -v
```

Expected: All 8 tests PASS

**Step 5: Commit**

```bash
git add shiprush/xml_builder.py tests/test_xml_builder.py
git commit -m "feat: add XML builder for ShipRush API request construction"
```

---

## Task 4: XML Parser

**Files:**
- Create: `shiprush/xml_parser.py`
- Create: `tests/test_xml_parser.py`
- Create: `tests/fixtures/` (directory)
- Create: `tests/fixtures/rate_response.xml`
- Create: `tests/fixtures/ship_response.xml`
- Create: `tests/fixtures/track_response.xml`
- Create: `tests/fixtures/void_response.xml`
- Create: `tests/fixtures/address_validate_response.xml`

**Step 1: Create test fixtures**

Create `tests/fixtures/rate_response.xml`:
```xml
<RateResponse>
  <ShipTransaction>
    <Shipment>
      <RateDetails>
        <Rate>
          <Carrier>FedEx</Carrier>
          <ServiceType>FedExGround</ServiceType>
          <ServiceDescription>FedEx Ground</ServiceDescription>
          <TotalCharges>12.50</TotalCharges>
          <Currency>USD</Currency>
          <EstimatedDeliveryDate>2026-04-03</EstimatedDeliveryDate>
        </Rate>
        <Rate>
          <Carrier>UPS</Carrier>
          <ServiceType>UPSGround</ServiceType>
          <ServiceDescription>UPS Ground</ServiceDescription>
          <TotalCharges>11.75</TotalCharges>
          <Currency>USD</Currency>
          <EstimatedDeliveryDate>2026-04-04</EstimatedDeliveryDate>
        </Rate>
      </RateDetails>
    </Shipment>
  </ShipTransaction>
</RateResponse>
```

Create `tests/fixtures/ship_response.xml`:
```xml
<ShipResponse>
  <ShipTransaction>
    <Shipment>
      <TrackingNumber>794644790132</TrackingNumber>
      <Carrier>FedEx</Carrier>
      <ServiceType>FedExGround</ServiceType>
      <ServiceDescription>FedEx Ground</ServiceDescription>
      <ShippingCharges>12.50</ShippingCharges>
      <Currency>USD</Currency>
      <LabelUrl>https://labels.shiprush.com/abc123.pdf</LabelUrl>
    </Shipment>
  </ShipTransaction>
</ShipResponse>
```

Create `tests/fixtures/track_response.xml`:
```xml
<TrackResponse>
  <ShipTransaction>
    <Shipment>
      <TrackingNumber>794644790132</TrackingNumber>
      <Carrier>FedEx</Carrier>
      <Status>In Transit</Status>
      <EstimatedDelivery>2026-04-03</EstimatedDelivery>
      <TrackingEvents>
        <Event>
          <Timestamp>2026-03-30T14:22:00Z</Timestamp>
          <Location>Memphis, TN</Location>
          <Description>Departed FedEx facility</Description>
        </Event>
        <Event>
          <Timestamp>2026-03-30T08:00:00Z</Timestamp>
          <Location>Seattle, WA</Location>
          <Description>Picked up</Description>
        </Event>
      </TrackingEvents>
    </Shipment>
  </ShipTransaction>
</TrackResponse>
```

Create `tests/fixtures/void_response.xml`:
```xml
<VoidResponse>
  <TrackingNumber>794644790132</TrackingNumber>
  <Voided>true</Voided>
  <Message>Shipment successfully voided</Message>
</VoidResponse>
```

Create `tests/fixtures/address_validate_response.xml`:
```xml
<AddressValidateResponse>
  <Valid>true</Valid>
  <CorrectedAddress>
    <Address>
      <Address1>123 MAIN ST</Address1>
      <City>SEATTLE</City>
      <State>WA</State>
      <PostalCode>98101-1234</PostalCode>
      <Country>US</Country>
    </Address>
  </CorrectedAddress>
</AddressValidateResponse>
```

**Step 2: Write the failing test**

Create `tests/test_xml_parser.py`:

```python
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
    assert result.message == "Shipment successfully voided"


def test_parse_address_validate_response():
    xml_str = (FIXTURES / "address_validate_response.xml").read_text()
    result = parse_address_validate_response(xml_str)
    assert result.valid is True
    assert result.corrected_address is not None
    assert result.corrected_address.street1 == "123 MAIN ST"
    assert result.corrected_address.postal_code == "98101-1234"
```

**Step 3: Run test to verify it fails**

```bash
pytest tests/test_xml_parser.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'shiprush.xml_parser'`

**Step 4: Write the implementation**

Create `shiprush/xml_parser.py`:

```python
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
```

**Step 5: Run test to verify it passes**

```bash
pytest tests/test_xml_parser.py -v
```

Expected: All 5 tests PASS

**Step 6: Commit**

```bash
git add shiprush/xml_parser.py tests/test_xml_parser.py tests/fixtures/
git commit -m "feat: add XML parser for ShipRush API responses"
```

---

## Task 5: ShipRush HTTP Client

**Files:**
- Create: `shiprush/client.py`
- Create: `tests/test_client.py`

**Step 1: Write the failing test**

Create `tests/test_client.py`:

```python
import pytest
from unittest.mock import AsyncMock, patch

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

VOID_XML = """<VoidResponse><TrackingNumber>794644790132</TrackingNumber>
<Voided>true</Voided><Message>Voided</Message></VoidResponse>"""

ADDR_XML = """<AddressValidateResponse><Valid>true</Valid>
<CorrectedAddress><Address><Address1>100 MAIN ST</Address1>
<City>SEATTLE</City><State>WA</State><PostalCode>98101-1234</PostalCode>
<Country>US</Country></Address></CorrectedAddress></AddressValidateResponse>"""


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
async def test_validate_address():
    client = ShipRushClient(token="test-token", base_url="https://sandbox.api.my.shiprush.com")
    with patch.object(client._http, "post", return_value=_mock_response(ADDR_XML)):
        result = await client.validate_address(ORIGIN)
        assert result.valid is True


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
    error_resp.raise_for_status.side_effect = Exception("HTTP 500")
    with patch.object(client._http, "post", return_value=error_resp):
        with pytest.raises(Exception, match="HTTP 500"):
            await client.get_rates(ORIGIN, DEST, PACKAGES)
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_client.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'shiprush.client'`

**Step 3: Write the implementation**

Create `shiprush/client.py`:

```python
import httpx

from shiprush.models import (
    Address,
    AddressValidationResult,
    Package,
    RateResult,
    ShipmentResult,
    TrackingResult,
    VoidResult,
)
from shiprush.xml_builder import (
    build_address_validate_request,
    build_rate_request,
    build_ship_request,
    build_void_request,
)
from shiprush.xml_parser import (
    parse_address_validate_response,
    parse_rate_response,
    parse_ship_response,
    parse_track_response,
    parse_void_response,
)


class ShipRushClient:
    def __init__(self, token: str, base_url: str):
        self._token = token
        self._base_url = base_url
        self._http = httpx.AsyncClient(timeout=30.0)

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "X-SHIPRUSH-SHIPPING-TOKEN": self._token,
            "Content-Type": "application/xml",
        }

    async def _post(self, path: str, body: str) -> str:
        url = f"{self._base_url}{path}"
        response = await self._http.post(url, content=body, headers=self._headers)
        response.raise_for_status()
        return response.text

    async def get_rates(
        self,
        origin: Address,
        destination: Address,
        packages: list[Package],
        carrier_filter: str | None = None,
    ) -> list[RateResult]:
        xml = build_rate_request(origin, destination, packages, carrier_filter)
        response_xml = await self._post("/shipmentservice.svc/shipment/rate", xml)
        return parse_rate_response(response_xml)

    async def create_shipment(
        self,
        origin: Address,
        destination: Address,
        packages: list[Package],
        carrier: str,
        service_name: str,
        reference: str | None = None,
    ) -> ShipmentResult:
        xml = build_ship_request(origin, destination, packages, carrier, service_name, reference)
        response_xml = await self._post("/shipmentservice.svc/shipment/ship", xml)
        return parse_ship_response(response_xml)

    async def track_shipment(
        self,
        tracking_number: str,
        carrier: str | None = None,
    ) -> TrackingResult:
        xml = f"<TrackRequest><TrackingNumber>{tracking_number}</TrackingNumber>"
        if carrier:
            xml += f"<Carrier>{carrier}</Carrier>"
        xml += "</TrackRequest>"
        response_xml = await self._post("/shipmentservice.svc/shipment/track", xml)
        return parse_track_response(response_xml)

    async def void_shipment(
        self,
        tracking_number: str,
        carrier: str | None = None,
    ) -> VoidResult:
        xml = build_void_request(tracking_number, carrier)
        response_xml = await self._post("/shipmentservice.svc/shipment/void", xml)
        return parse_void_response(response_xml)

    async def validate_address(self, address: Address) -> AddressValidationResult:
        xml = build_address_validate_request(address)
        response_xml = await self._post("/shipmentservice.svc/address/validate", xml)
        return parse_address_validate_response(response_xml)
```

**Step 4: Run test to verify it passes**

```bash
pytest tests/test_client.py -v
```

Expected: All 7 tests PASS

**Step 5: Commit**

```bash
git add shiprush/client.py tests/test_client.py
git commit -m "feat: add async ShipRush HTTP client with XML request/response handling"
```

---

## Task 6: FastMCP Server with 5 Tools

**Files:**
- Create: `server.py`

**Step 1: Write `server.py`**

```python
from mcp.server.fastmcp import FastMCP

from config import config
from shiprush.client import ShipRushClient
from shiprush.models import Address, Package

mcp = FastMCP(
    name="shiprush-mcp-server",
    host="0.0.0.0",
    stateless_http=True,
)

client = ShipRushClient(token=config.shipping_token, base_url=config.base_url)


@mcp.tool()
async def get_shipping_rates(
    origin_name: str | None = None,
    origin_company: str | None = None,
    origin_street1: str = "",
    origin_street2: str | None = None,
    origin_city: str = "",
    origin_state: str = "",
    origin_postal_code: str = "",
    origin_country: str = "US",
    destination_name: str | None = None,
    destination_company: str | None = None,
    destination_street1: str = "",
    destination_street2: str | None = None,
    destination_city: str = "",
    destination_state: str = "",
    destination_postal_code: str = "",
    destination_country: str = "US",
    package_weight_lb: float = 1.0,
    package_length_in: float | None = None,
    package_width_in: float | None = None,
    package_height_in: float | None = None,
    carrier_filter: str | None = None,
) -> dict:
    """Get shipping rate quotes across carriers (FedEx, UPS, USPS). Returns available services with prices and estimated delivery dates. Use this before create_shipment to find the best carrier and service_name."""
    origin = Address(name=origin_name, company=origin_company, street1=origin_street1, street2=origin_street2, city=origin_city, state=origin_state, postal_code=origin_postal_code, country=origin_country)
    destination = Address(name=destination_name, company=destination_company, street1=destination_street1, street2=destination_street2, city=destination_city, state=destination_state, postal_code=destination_postal_code, country=destination_country)
    packages = [Package(weight_lb=package_weight_lb, length_in=package_length_in, width_in=package_width_in, height_in=package_height_in)]
    try:
        rates = await client.get_rates(origin, destination, packages, carrier_filter)
        return {"rates": [r.model_dump() for r in rates]}
    except Exception as e:
        return {"error": str(e), "code": "RATE_ERROR"}


@mcp.tool()
async def create_shipment(
    origin_name: str | None = None,
    origin_company: str | None = None,
    origin_street1: str = "",
    origin_street2: str | None = None,
    origin_city: str = "",
    origin_state: str = "",
    origin_postal_code: str = "",
    origin_country: str = "US",
    destination_name: str | None = None,
    destination_company: str | None = None,
    destination_street1: str = "",
    destination_street2: str | None = None,
    destination_city: str = "",
    destination_state: str = "",
    destination_postal_code: str = "",
    destination_country: str = "US",
    package_weight_lb: float = 1.0,
    package_length_in: float | None = None,
    package_width_in: float | None = None,
    package_height_in: float | None = None,
    carrier: str = "",
    service_name: str = "",
    reference: str | None = None,
) -> dict:
    """Create a shipment and generate a shipping label. Returns tracking number, label URL, and cost. Call get_shipping_rates first to find the carrier and service_name values."""
    origin = Address(name=origin_name, company=origin_company, street1=origin_street1, street2=origin_street2, city=origin_city, state=origin_state, postal_code=origin_postal_code, country=origin_country)
    destination = Address(name=destination_name, company=destination_company, street1=destination_street1, street2=destination_street2, city=destination_city, state=destination_state, postal_code=destination_postal_code, country=destination_country)
    packages = [Package(weight_lb=package_weight_lb, length_in=package_length_in, width_in=package_width_in, height_in=package_height_in)]
    try:
        result = await client.create_shipment(origin, destination, packages, carrier, service_name, reference)
        return result.model_dump()
    except Exception as e:
        return {"error": str(e), "code": "SHIP_ERROR"}


@mcp.tool()
async def track_shipment(
    tracking_number: str,
    carrier: str | None = None,
) -> dict:
    """Get tracking status and scan history for a shipment. Returns current status, estimated delivery, and event history."""
    try:
        result = await client.track_shipment(tracking_number, carrier)
        return result.model_dump()
    except Exception as e:
        return {"error": str(e), "code": "TRACK_ERROR"}


@mcp.tool()
async def void_shipment(
    tracking_number: str,
    carrier: str | None = None,
) -> dict:
    """Cancel/void a shipping label. Returns whether the void was successful."""
    try:
        result = await client.void_shipment(tracking_number, carrier)
        return result.model_dump()
    except Exception as e:
        return {"error": str(e), "code": "VOID_ERROR"}


@mcp.tool()
async def validate_address(
    street1: str,
    city: str,
    state: str,
    postal_code: str,
    country: str = "US",
    name: str | None = None,
    company: str | None = None,
    street2: str | None = None,
) -> dict:
    """Validate and correct a shipping address. Returns whether the address is valid, a corrected version if available, and any errors."""
    address = Address(name=name, company=company, street1=street1, street2=street2, city=city, state=state, postal_code=postal_code, country=country)
    try:
        result = await client.validate_address(address)
        return result.model_dump()
    except Exception as e:
        return {"error": str(e), "code": "VALIDATION_ERROR"}


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
```

**Step 2: Verify server starts locally**

```bash
export SHIPRUSH_SHIPPING_TOKEN="test-placeholder"
python server.py &
sleep 2
curl -s -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}'
kill %1
```

Expected: JSON response listing 5 tools: `get_shipping_rates`, `create_shipment`, `track_shipment`, `void_shipment`, `validate_address`

**Step 3: Verify tool schemas have no `$ref`**

Inspect the `tools/list` response and confirm all tool `inputSchema` objects are fully inlined — no `$ref`, `$defs`, `$anchor`, or `$dynamicRef` keywords anywhere. This is a hard AgentCore requirement.

If any `$ref` appears, flatten the schema by inlining the address/package fields as top-level parameters (which is why the tool functions use flat parameters instead of nested Pydantic objects).

**Step 4: Commit**

```bash
git add server.py
git commit -m "feat: add FastMCP server with 5 ShipRush shipping tools"
```

---

## Task 7: Run All Tests & Final Verification

**Step 1: Run full test suite**

```bash
pytest tests/ -v
```

Expected: All 20 tests PASS (8 models + 8 xml_builder + 5 xml_parser + 7 client — numbers are approximate, adjust if you added more)

**Step 2: Start server and test with MCP Inspector**

```bash
export SHIPRUSH_SHIPPING_TOKEN="your-real-sandbox-token"
python server.py
```

In another terminal:
```bash
npx @modelcontextprotocol/inspector
```

Connect to `http://localhost:8000/mcp` and verify:
1. `tools/list` returns 5 tools with correct descriptions
2. All tool schemas are flat (no `$ref`)
3. Test `validate_address` with a real address against sandbox
4. Test `get_shipping_rates` with real origin/destination against sandbox

**Step 3: Commit any fixes**

```bash
git add -A
git commit -m "fix: address issues found during integration testing"
```

---

## Task 8: AgentCore Deployment (Manual — not automated)

This task is performed by the developer, not by Claude. Instructions for reference.

**Step 1: Install AgentCore toolkit**

```bash
pip install bedrock-agentcore-starter-toolkit
```

**Step 2: Configure**

```bash
agentcore configure \
  --entrypoint server.py \
  --requirements-file requirements.txt \
  --protocol MCP \
  --name shiprush-mcp-server \
  --disable-memory --disable-otel \
  --deployment-type container
```

When prompted:
- IAM execution role: create or provide existing
- ECR registry: let it auto-create
- OAuth: skip for now (internal use)

**Step 3: Set environment variables**

Edit the generated `.bedrock_agentcore.yaml` to include:
```yaml
environment:
  SHIPRUSH_SHIPPING_TOKEN: "your-production-token"
  SHIPRUSH_BASE_URL: "https://api.my.shiprush.com"
```

**Step 4: Deploy**

```bash
agentcore launch --agent shiprush-mcp-server
```

Expected output: `arn:aws:bedrock-agentcore:{region}:{account}:runtime/shiprush-mcp-server-xxxxx`

**Step 5: Smoke test deployed server**

```bash
export SERVER_ARN="arn:aws:bedrock-agentcore:us-west-2:ACCOUNT:runtime/shiprush-mcp-server-xxxxx"

aws bedrock-agentcore invoke-agent-runtime \
  --agent-runtime-arn $SERVER_ARN \
  --content-type "application/json" \
  --accept "application/json, text/event-stream" \
  --payload '{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}' \
  output.txt

cat output.txt
```

Expected: JSON listing 5 tools

---

## Summary

| Task | What | Tests |
|------|------|-------|
| 1 | Project scaffolding, config, .gitignore | — |
| 2 | Pydantic models (Address, Package, results) | 8 unit tests |
| 3 | XML builder (rate, ship, void, address) | 8 unit tests |
| 4 | XML parser (rate, ship, track, void, address) | 5 unit tests |
| 5 | Async HTTP client | 7 unit tests (mocked HTTP) |
| 6 | FastMCP server with 5 tools | Manual: tools/list + schema check |
| 7 | Full test suite + sandbox integration | All tests + MCP Inspector |
| 8 | AgentCore deployment | Manual: deploy + smoke test |

**Total implementation tasks:** 8 (Tasks 1-7 are automatable, Task 8 is manual deployment)
