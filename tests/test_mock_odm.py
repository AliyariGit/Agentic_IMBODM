"""
Tests for the mock ODM rule engine.

Run without any external dependencies:
    pip install pytest httpx fastapi
    pytest tests/test_mock_odm.py -v
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient
from mock_odm_server import app

client = TestClient(app)


def authorize(payload: dict) -> dict:
    r = client.post("/api/authorize", json=payload)
    assert r.status_code == 200
    return r.json()


BASE = {
    "transactionAmount": 10.00,
    "cardNumber": "4532015112830366",   # valid Luhn
    "merchantId": "test_merchant",
    "mcc": "5812",
    "country": "CA",
    "entryMode": "CHIP",
}


class TestApprovedPath:
    def test_standard_chip_transaction(self):
        result = authorize(BASE)
        assert result["decision"] == "APPROVED"
        assert result["responseCode"] == "00"
        assert result["authorizationCode"] is not None
        assert len(result["authorizationCode"]) == 6

    def test_audit_trail_all_pass(self):
        result = authorize(BASE)
        for trace in result["auditTrail"]:
            assert trace["result"] == "PASS"

    def test_contactless_under_limit(self):
        result = authorize({**BASE, "entryMode": "NFC_CONTACTLESS", "transactionAmount": 9.99})
        assert result["decision"] == "APPROVED"


class TestAmountLimitRule:
    def test_exactly_at_limit(self):
        result = authorize({**BASE, "transactionAmount": 10_000.00})
        assert result["decision"] == "APPROVED"

    def test_one_cent_over_limit(self):
        result = authorize({**BASE, "transactionAmount": 10_000.01})
        assert result["decision"] == "DECLINED"
        assert result["responseCode"] == "05"
        assert "AmountLimitRule" in [t["ruleName"] for t in result["auditTrail"]]

    def test_large_amount_declined(self):
        result = authorize({**BASE, "transactionAmount": 50_000})
        assert result["decision"] == "DECLINED"


class TestCountryBlacklistRule:
    @pytest.mark.parametrize("country", ["KP", "IR", "CU", "SY", "RU", "BY"])
    def test_sanctioned_countries(self, country):
        result = authorize({**BASE, "country": country})
        assert result["decision"] == "DECLINED"
        fired = [t for t in result["auditTrail"] if t["ruleName"] == "CountryBlacklistRule"]
        assert fired[0]["fired"] is True

    def test_permitted_country(self):
        result = authorize({**BASE, "country": "US"})
        assert result["decision"] == "APPROVED"


class TestMCCRestrictionRule:
    def test_gambling_mcc_declined(self):
        result = authorize({**BASE, "mcc": "7995"})
        assert result["decision"] == "DECLINED"

    def test_lottery_mcc_declined(self):
        result = authorize({**BASE, "mcc": "9754"})
        assert result["decision"] == "DECLINED"

    def test_restaurant_mcc_approved(self):
        result = authorize({**BASE, "mcc": "5812"})
        assert result["decision"] == "APPROVED"


class TestCardValidityRule:
    def test_invalid_luhn_declined(self):
        result = authorize({**BASE, "cardNumber": "1234567890123456"})
        assert result["decision"] == "DECLINED"
        fired = [t for t in result["auditTrail"] if t["ruleName"] == "CardValidityRule"]
        assert fired[0]["fired"] is True

    def test_valid_luhn_approved(self):
        result = authorize({**BASE, "cardNumber": "5500005555555559"})
        assert result["decision"] == "APPROVED"


class TestContactlessLimitRule:
    def test_contactless_over_250_declined(self):
        result = authorize({**BASE, "entryMode": "NFC_CONTACTLESS", "transactionAmount": 250.01})
        assert result["decision"] == "DECLINED"
        fired = [t for t in result["auditTrail"] if t["ruleName"] == "ContactlessLimitRule"]
        assert fired[0]["fired"] is True

    def test_chip_over_250_approved(self):
        result = authorize({**BASE, "entryMode": "CHIP", "transactionAmount": 300.00})
        assert result["decision"] == "APPROVED"


class TestShortCircuit:
    def test_first_failing_rule_stops_execution(self):
        """Amount limit rule fires first; only 1 trace should be in audit trail."""
        result = authorize({**BASE, "transactionAmount": 99_999, "country": "RU"})
        assert result["decision"] == "DECLINED"
        # Short-circuit: stops at AmountLimitRule, never reaches CountryBlacklistRule
        rule_names = [t["ruleName"] for t in result["auditTrail"]]
        assert rule_names == ["AmountLimitRule"]
