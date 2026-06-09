"""
MCP (Model Context Protocol) server — exposes IBM ODM as an MCP tool.

This lets any MCP-compatible client (Claude Desktop, other AI agents)
call the payment authorization engine without knowing its HTTP details.

Run:
    python mcp_odm_server.py
"""

import os
import requests
from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv

load_dotenv()

ODM_ENDPOINT = os.getenv("ODM_ENDPOINT", "http://localhost:8080/api/authorize")

mcp = FastMCP("IBM ODM Payment Authorization")


@mcp.tool()
def authorize_payment(
    amount: float,
    card_number: str,
    merchant_id: str,
    mcc: str,
    country: str,
    entry_mode: str = "CHIP",
    currency: str = "CAD",
) -> dict:
    """
    Authorize a payment transaction via IBM ODM Rule Execution Server.

    Args:
        amount: Transaction amount in the specified currency
        card_number: 16-digit card number (pad with leading zeros if only last-4 known)
        merchant_id: Merchant identifier
        mcc: ISO 18245 Merchant Category Code (4 digits, e.g. '5812' for restaurants)
        country: ISO 3166-1 alpha-2 merchant country code (e.g. 'CA', 'US')
        entry_mode: CHIP | NFC_CONTACTLESS | SWIPE | MANUAL
        currency: ISO 4217 code (default CAD)

    Returns:
        Authorization result with decision, response code, and full audit trail.
    """
    payload = {
        "transactionAmount": amount,
        "cardNumber": card_number,
        "merchantId": merchant_id,
        "mcc": mcc,
        "country": country,
        "entryMode": entry_mode,
        "currency": currency,
    }
    r = requests.post(ODM_ENDPOINT, json=payload, timeout=5)
    r.raise_for_status()
    return r.json()


@mcp.resource("odm://rules/summary")
def get_rules_summary() -> str:
    """Returns a plain-English summary of the active ODM ruleflow."""
    return """
    Active Payment Authorization Ruleflow (5 rules, sequential):

    1. AmountLimitRule      — Decline if amount > $10,000 CAD
    2. CountryBlacklistRule — Decline if country is OFAC-sanctioned (KP, IR, CU, SY, RU, BY)
    3. MCCRestrictionRule   — Decline restricted merchant categories (gambling: 7995, lottery: 9754)
    4. CardValidityRule     — Decline if card number fails Luhn algorithm
    5. ContactlessLimitRule — Decline NFC/contactless transactions over $250 CAD

    Rules short-circuit: first DECLINED result stops processing.
    All fired rules are captured in the audit trail regardless.
    """


if __name__ == "__main__":
    mcp.run()
