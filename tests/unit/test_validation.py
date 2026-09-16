"""Unit tests for input validation and quality gates."""

from __future__ import annotations

import datetime as dt
import pytest

from app.config import AppConfig
from app.domain.errors import InvalidGatewayIdError, InvalidRequestError
from app.validation.input import (
    DataQualityGate,
    validate_hex_gateway_id,
    validate_iso_date,
)


def test_validate_iso_date_valid():
    d = validate_iso_date("2026-03-23")
    assert d == dt.date(2026, 3, 23)


def test_validate_iso_date_invalid():
    with pytest.raises(InvalidRequestError):
        validate_iso_date("2026/03/23")
    with pytest.raises(InvalidRequestError):
        validate_iso_date("not-a-date")


def test_validate_hex_gateway_id_valid():
    assert validate_hex_gateway_id("0202CB0A6B1F") == "0202CB0A6B1F"
    assert validate_hex_gateway_id("02:02:cb:0a:6b:1f") == "0202CB0A6B1F"


def test_validate_hex_gateway_id_invalid():
    with pytest.raises(InvalidGatewayIdError):
        validate_hex_gateway_id("XYZ123456789")
    with pytest.raises(InvalidGatewayIdError):
        validate_hex_gateway_id("0202")
