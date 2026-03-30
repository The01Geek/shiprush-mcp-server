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
