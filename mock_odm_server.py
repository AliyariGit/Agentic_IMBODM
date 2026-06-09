"""
Mock IBM ODM Rule Execution Server (FastAPI)

Simulates the 5-rule sequential ruleflow that real ODM would execute.
Exposes the same REST contract as the HTDS endpoint so the agent layer
needs zero changes when pointed at a real ODM instance.

Run:
    uvicorn mock_odm_server:app --port 8080 --reload
"""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import datetime
import hashlib
import os

app = FastAPI(title="IBM ODM Mock — Payment Authorization RES")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Domain models (mirrors the Java BOM / XOM)
# ---------------------------------------------------------------------------

class TransactionRequest(BaseModel):
    transactionAmount: float
    cardNumber: str
    merchantId: str
    mcc: str                        # ISO 18245 Merchant Category Code
    country: str                    # ISO 3166-1 alpha-2
    entryMode: Optional[str] = "CHIP"
    currency: Optional[str] = "CAD"

class RuleTrace(BaseModel):
    ruleName: str
    fired: bool
    result: str
    message: str

class AuthorizationResponse(BaseModel):
    decision: str                   # APPROVED | DECLINED
    responseCode: str               # ISO 8583 response code
    authorizationCode: Optional[str]
    declineReason: Optional[str]
    auditTrail: list[RuleTrace]

# ---------------------------------------------------------------------------
# Rule implementations (mirrors BAL rules in Decision Center)
# ---------------------------------------------------------------------------

HIGH_RISK_COUNTRIES = {"KP", "IR", "CU", "SY", "RU", "BY"}
BLOCKED_MCC_CODES = {"7995", "9754"}   # gambling, lottery

def _luhn_check(card: str) -> bool:
    """Luhn algorithm — mirrors 'Card Validity Check' rule in ODM."""
    digits = [int(d) for d in card.replace(" ", "") if d.isdigit()]
    digits.reverse()
    total = 0
    for i, d in enumerate(digits):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0

def rule_1_amount_limit(req: TransactionRequest) -> RuleTrace:
    """Rule: Decline if single transaction exceeds $10,000 CAD."""
    fired = req.transactionAmount > 10_000
    return RuleTrace(
        ruleName="AmountLimitRule",
        fired=fired,
        result="DECLINED" if fired else "PASS",
        message=f"Amount ${req.transactionAmount:.2f} {'exceeds' if fired else 'within'} $10,000 limit"
    )

def rule_2_country_blacklist(req: TransactionRequest) -> RuleTrace:
    """Rule: Decline if merchant country is OFAC-sanctioned."""
    fired = req.country.upper() in HIGH_RISK_COUNTRIES
    return RuleTrace(
        ruleName="CountryBlacklistRule",
        fired=fired,
        result="DECLINED" if fired else "PASS",
        message=f"Country '{req.country}' {'is OFAC-restricted' if fired else 'is permitted'}"
    )

def rule_3_mcc_restriction(req: TransactionRequest) -> RuleTrace:
    """Rule: Decline blocked merchant category codes."""
    fired = req.mcc in BLOCKED_MCC_CODES
    return RuleTrace(
        ruleName="MCCRestrictionRule",
        fired=fired,
        result="DECLINED" if fired else "PASS",
        message=f"MCC {req.mcc} {'is restricted' if fired else 'is permitted'}"
    )

def rule_4_card_validity(req: TransactionRequest) -> RuleTrace:
    """Rule: Decline if card number fails Luhn check."""
    valid = _luhn_check(req.cardNumber)
    fired = not valid
    return RuleTrace(
        ruleName="CardValidityRule",
        fired=fired,
        result="DECLINED" if fired else "PASS",
        message=f"Card {'failed' if fired else 'passed'} Luhn validation"
    )

def rule_5_contactless_limit(req: TransactionRequest) -> RuleTrace:
    """Rule: Contactless/NFC transactions capped at $250 CAD (PCI-DSS)."""
    is_contactless = req.entryMode in {"NFC_CONTACTLESS", "CONTACTLESS"}
    fired = is_contactless and req.transactionAmount > 250
    return RuleTrace(
        ruleName="ContactlessLimitRule",
        fired=fired,
        result="DECLINED" if fired else "PASS",
        message=(
            f"Contactless limit exceeded (${req.transactionAmount:.2f} > $250)"
            if fired else
            "Contactless limit check passed"
        )
    )

# ---------------------------------------------------------------------------
# HTDS REST endpoint — mirrors PaymentAuthorizationResource.java
# ---------------------------------------------------------------------------

@app.post("/api/authorize", response_model=AuthorizationResponse)
def authorize(req: TransactionRequest) -> AuthorizationResponse:
    """
    Executes the 5-rule ruleflow sequentially (short-circuit on first DECLINED).
    This is the endpoint the Python agent calls via the authorize_payment tool.
    """
    rules = [
        rule_1_amount_limit,
        rule_2_country_blacklist,
        rule_3_mcc_restriction,
        rule_4_card_validity,
        rule_5_contactless_limit,
    ]

    audit_trail: list[RuleTrace] = []
    decline_trace: Optional[RuleTrace] = None

    for rule_fn in rules:
        trace = rule_fn(req)
        audit_trail.append(trace)
        if trace.result == "DECLINED":
            decline_trace = trace
            break   # ruleflow short-circuit

    if decline_trace:
        return AuthorizationResponse(
            decision="DECLINED",
            responseCode="05",  # ISO 8583 — Do Not Honor
            authorizationCode=None,
            declineReason=decline_trace.message,
            auditTrail=audit_trail,
        )

    # Generate deterministic auth code from card + merchant + timestamp
    seed = f"{req.cardNumber}{req.merchantId}{datetime.date.today()}"
    auth_code = hashlib.sha256(seed.encode()).hexdigest()[:6].upper()

    return AuthorizationResponse(
        decision="APPROVED",
        responseCode="00",  # ISO 8583 — Approved
        authorizationCode=auth_code,
        declineReason=None,
        auditTrail=audit_trail,
    )


@app.get("/health")
def health():
    return {"status": "ok", "engine": "IBM ODM Mock RES v1.0"}


_BASE_DIR = os.path.dirname(os.path.abspath(__file__))

@app.get("/")
def ui():
    return FileResponse(os.path.join(_BASE_DIR, "web", "index.html"))
