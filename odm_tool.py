"""
LangChain tool definition for IBM ODM Rule Execution Server.

The agent calls this tool after extracting structured fields from
the user's natural-language payment request.
"""

import os
import requests
from langchain.tools import tool
from dotenv import load_dotenv

load_dotenv()

ODM_ENDPOINT = os.getenv("ODM_ENDPOINT", "http://localhost:8080/api/authorize")


@tool
def authorize_payment(
    amount: float,
    card_number: str,
    merchant_id: str,
    merchant_category_code: str,
    country: str,
    entry_mode: str = "CHIP",
    currency: str = "CAD",
) -> dict:
    """
    Calls IBM ODM Rule Execution Server to authorize a payment transaction.

    Args:
        amount: Transaction amount (e.g. 4.50)
        card_number: Full card number or last-4 padded to 16 digits
        merchant_id: Merchant identifier string
        merchant_category_code: ISO 18245 MCC (e.g. '5812' for restaurants)
        country: ISO 3166-1 alpha-2 country code (e.g. 'CA', 'US')
        entry_mode: How the card was presented — CHIP, NFC_CONTACTLESS, SWIPE, MANUAL
        currency: ISO 4217 currency code (default CAD)

    Returns:
        dict with keys: decision, responseCode, authorizationCode,
        declineReason, auditTrail
    """
    payload = {
        "transactionAmount": amount,
        "cardNumber": card_number,
        "merchantId": merchant_id,
        "mcc": merchant_category_code,
        "country": country,
        "entryMode": entry_mode,
        "currency": currency,
    }
    try:
        response = requests.post(ODM_ENDPOINT, json=payload, timeout=5)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.ConnectionError:
        return {
            "error": "ODM server unreachable",
            "detail": f"Could not connect to {ODM_ENDPOINT}. "
                      "Start the mock server: uvicorn mock_odm_server:app --port 8080"
        }
    except requests.exceptions.Timeout:
        return {"error": "ODM server timeout", "detail": "Request exceeded 5s limit"}
    except requests.exceptions.HTTPError as e:
        return {"error": "ODM HTTP error", "detail": str(e)}
