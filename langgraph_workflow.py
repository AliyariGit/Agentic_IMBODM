"""
LangGraph multi-step payment authorization workflow.

Graph structure:
    START
      │
      ▼
    [extract_intent]        ← LLM: natural language → structured fields
      │
      ▼
    [check_completeness]    ← router: all required fields present?
      │ complete    │ missing
      │             ▼
      │       [request_clarification] → END
      │
      ▼
    [validate_input]        ← amount > 0, valid card digits, 2-char ISO country
      │ valid    │ errors
      │          ▼
      │     [format_error] → END
      │
      ▼
    [enrich_mcc]            ← infer ISO 18245 MCC from merchant name if absent
      │
      ▼
    [call_odm]              ← POST to IBM ODM HTDS REST endpoint
      │
      ▼
    [format_response]       ← ODM JSON → plain-language answer
      │
      ▼
     END
"""

import json
import os
import re
from operator import add as list_add
from typing import Annotated, Optional, TypedDict

import requests
from dotenv import load_dotenv
from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.graph import END, START, StateGraph

load_dotenv()

ODM_ENDPOINT = os.getenv("ODM_ENDPOINT", "http://localhost:9090/api/authorize")


# ── State ─────────────────────────────────────────────────────────────────────

class PaymentState(TypedDict):
    messages:          Annotated[list[BaseMessage], list_add]
    raw_input:         str
    extracted:         dict        # amount, card_number, merchant_id, mcc, country, entry_mode
    missing_fields:    list[str]
    validation_errors: list[str]
    odm_response:      Optional[dict]
    final_answer:      str
    step_trace:        Annotated[list[str], list_add]


# ── LLM factory ───────────────────────────────────────────────────────────────

def _get_llm():
    mode = os.getenv("LLM_MODE", "azure").lower()
    if mode == "ollama":
        from langchain_community.chat_models import ChatOllama
        return ChatOllama(
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            model=os.getenv("OLLAMA_MODEL", "phi3"),
            temperature=0,
        )
    from langchain_openai import AzureChatOpenAI
    return AzureChatOpenAI(
        azure_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4"),
        api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01"),
        temperature=0,
    )


# ── Node 1: extract_intent ────────────────────────────────────────────────────

_EXTRACT_PROMPT = """Extract payment transaction fields from the user message.
Return a single JSON object with these keys (use null for unknowns):

  amount           (float)   transaction amount
  card_number      (string)  full 16-digit number, or last-4 padded: "000000000000<last4>"
  merchant_id      (string)  slug of merchant name, e.g. "java_joe_coffee"
  mcc              (string)  ISO 18245 4-digit code if determinable, else null
  country          (string)  ISO 3166-1 alpha-2 (default "CA" if not mentioned)
  entry_mode       (string)  CHIP | NFC_CONTACTLESS | SWIPE | MANUAL (default "CHIP")

MCC hints: 5812=restaurant/cafe, 5411=grocery, 5541=gas, 5732=electronics,
           5912=pharmacy, 5311=department store, 7011=hotel, 4111=transit, 5999=misc

Return only the JSON object — no markdown, no explanation.

Message: {input}"""


def extract_intent_node(state: PaymentState) -> dict:
    llm = _get_llm()
    prompt = _EXTRACT_PROMPT.format(input=state["raw_input"])
    response = llm.invoke([HumanMessage(content=prompt)])

    text = response.content.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    try:
        extracted = json.loads(text)
    except json.JSONDecodeError:
        extracted = {}

    return {
        "extracted": extracted,
        "messages": [response],
        "step_trace": ["extract_intent"],
    }


# ── Node 2: check_completeness (router) ───────────────────────────────────────

_REQUIRED = ["amount", "card_number", "merchant_id", "country"]


def check_completeness_node(state: PaymentState) -> dict:
    missing = [f for f in _REQUIRED if not state.get("extracted", {}).get(f)]
    return {
        "missing_fields": missing,
        "step_trace": ["check_completeness"],
    }


def _route_completeness(state: PaymentState) -> str:
    return "request_clarification" if state["missing_fields"] else "validate_input"


# ── Node 3: request_clarification ─────────────────────────────────────────────

_FIELD_LABELS = {
    "amount": "transaction amount",
    "card_number": "card number (or last 4 digits)",
    "merchant_id": "merchant name",
    "country": "merchant country (e.g. CA, US)",
}


def request_clarification_node(state: PaymentState) -> dict:
    labels = [_FIELD_LABELS.get(f, f) for f in state["missing_fields"]]
    answer = (
        "I need a few more details to process this transaction. "
        f"Could you provide: {', '.join(labels)}?"
    )
    return {"final_answer": answer, "step_trace": ["request_clarification"]}


# ── Node 4: validate_input ────────────────────────────────────────────────────

def validate_input_node(state: PaymentState) -> dict:
    e = state.get("extracted", {})
    errors: list[str] = []

    try:
        if float(e.get("amount", 0)) <= 0:
            errors.append("Amount must be greater than zero")
    except (TypeError, ValueError):
        errors.append("Amount is not a valid number")

    card = str(e.get("card_number", "")).replace(" ", "")
    if not card.isdigit() or len(card) < 4:
        errors.append("Card number must contain at least 4 digits")

    country = str(e.get("country", "")).upper()
    if len(country) != 2 or not country.isalpha():
        errors.append("Country must be a valid 2-letter ISO code (e.g. CA, US)")

    return {"validation_errors": errors, "step_trace": ["validate_input"]}


def _route_validation(state: PaymentState) -> str:
    return "format_error" if state["validation_errors"] else "enrich_mcc"


# ── Node 5: format_error ──────────────────────────────────────────────────────

def format_error_node(state: PaymentState) -> dict:
    bullets = "\n".join(f"• {e}" for e in state["validation_errors"])
    return {
        "final_answer": f"Could not process transaction:\n{bullets}",
        "step_trace": ["format_error"],
    }


# ── Node 6: enrich_mcc ────────────────────────────────────────────────────────

_MCC_KEYWORDS: dict[str, str] = {
    "coffee": "5812", "cafe": "5812", "restaurant": "5812",
    "grocery": "5411", "supermarket": "5411", "sobeys": "5411", "loblaws": "5411",
    "gas": "5541", "petro": "5541", "esso": "5541", "shell": "5541",
    "pharmacy": "5912", "shoppers": "5912", "rexall": "5912",
    "electronics": "5732", "best buy": "5732", "apple store": "5732",
    "hotel": "7011", "inn": "7011", "marriott": "7011", "hilton": "7011",
    "transit": "4111", "ttc": "4111", "presto": "4111",
    "department": "5311", "walmart": "5311", "costco": "5311",
}


def enrich_mcc_node(state: PaymentState) -> dict:
    e = state["extracted"]
    mcc = e.get("mcc")

    if not mcc:
        merchant = str(e.get("merchant_id", "")).lower().replace("_", " ")
        for keyword, code in _MCC_KEYWORDS.items():
            if keyword in merchant:
                mcc = code
                break
        mcc = mcc or "5999"

    return {
        "extracted": {**e, "mcc": mcc},
        "step_trace": ["enrich_mcc"],
    }


# ── Node 7: call_odm ──────────────────────────────────────────────────────────

def call_odm_node(state: PaymentState) -> dict:
    e = state["extracted"]

    card = str(e.get("card_number", "0000000000000000")).replace(" ", "")
    if len(card) < 16:
        card = card.zfill(16)

    payload = {
        "transactionAmount": float(e.get("amount", 0)),
        "cardNumber": card,
        "merchantId": str(e.get("merchant_id", "unknown")),
        "mcc": str(e.get("mcc", "5999")),
        "country": str(e.get("country", "CA")).upper(),
        "entryMode": str(e.get("entry_mode", "CHIP")),
    }

    try:
        r = requests.post(ODM_ENDPOINT, json=payload, timeout=5)
        r.raise_for_status()
        odm_response = r.json()
    except requests.exceptions.ConnectionError:
        odm_response = {
            "error": "ODM server unreachable",
            "detail": f"Start mock server: uvicorn mock_odm_server:app --port 9090",
        }
    except Exception as exc:
        odm_response = {"error": str(exc)}

    return {"odm_response": odm_response, "step_trace": ["call_odm"]}


# ── Node 8: format_response ───────────────────────────────────────────────────

def format_response_node(state: PaymentState) -> dict:
    odm = state.get("odm_response", {})
    e = state.get("extracted", {})

    if odm.get("error"):
        answer = f"Unable to process transaction: {odm['error']}. {odm.get('detail', '')}"
        return {"final_answer": answer, "step_trace": ["format_response"]}

    amount = e.get("amount", "?")
    merchant = str(e.get("merchant_id", "the merchant")).replace("_", " ").title()
    decision = odm.get("decision", "UNKNOWN")

    if decision == "APPROVED":
        auth = odm.get("authorizationCode", "N/A")
        rules_passed = len(odm.get("auditTrail", []))
        answer = (
            f"Your ${amount:.2f} payment at {merchant} was approved. "
            f"Authorization code: {auth}. "
            f"All {rules_passed} compliance checks passed."
        )
    else:
        reason = odm.get("declineReason", "Policy restriction")
        rc = odm.get("responseCode", "05")
        fired = next(
            (t["ruleName"] for t in odm.get("auditTrail", []) if t.get("fired")),
            "policy rule",
        )
        answer = (
            f"Your ${amount:.2f} payment at {merchant} was declined. "
            f"Reason: {reason} (ISO 8583 code {rc}, triggered by {fired})."
        )

    return {"final_answer": answer, "step_trace": ["format_response"]}


# ── Build & compile the graph ─────────────────────────────────────────────────

def build_workflow():
    g = StateGraph(PaymentState)

    g.add_node("extract_intent",        extract_intent_node)
    g.add_node("check_completeness",    check_completeness_node)
    g.add_node("request_clarification", request_clarification_node)
    g.add_node("validate_input",        validate_input_node)
    g.add_node("format_error",          format_error_node)
    g.add_node("enrich_mcc",            enrich_mcc_node)
    g.add_node("call_odm",              call_odm_node)
    g.add_node("format_response",       format_response_node)

    g.add_edge(START,                   "extract_intent")
    g.add_edge("extract_intent",        "check_completeness")
    g.add_conditional_edges("check_completeness",  _route_completeness)
    g.add_edge("request_clarification", END)
    g.add_conditional_edges("validate_input",      _route_validation)
    g.add_edge("format_error",          END)
    g.add_edge("enrich_mcc",            "call_odm")
    g.add_edge("call_odm",              "format_response")
    g.add_edge("format_response",       END)

    return g.compile()


# ── Public entry point ────────────────────────────────────────────────────────

def run_workflow(user_message: str) -> PaymentState:
    """Run the full workflow from a natural-language payment message."""
    workflow = build_workflow()
    initial: PaymentState = {
        "messages": [HumanMessage(content=user_message)],
        "raw_input": user_message,
        "extracted": {},
        "missing_fields": [],
        "validation_errors": [],
        "odm_response": None,
        "final_answer": "",
        "step_trace": [],
    }
    return workflow.invoke(initial)


def run_workflow_from_fields(fields: dict) -> PaymentState:
    """
    Run the workflow starting from validate_input — skips the LLM extraction step.
    Used by the web dashboard and tests (no Azure credentials needed).
    """
    workflow = build_workflow()

    # Inject extracted fields and bypass the LLM nodes by patching the initial state.
    # We override extract_intent to be a pass-through when fields are pre-supplied.
    initial: PaymentState = {
        "messages": [],
        "raw_input": "",
        "extracted": fields,
        "missing_fields": [],
        "validation_errors": [],
        "odm_response": None,
        "final_answer": "",
        "step_trace": [],
    }

    # Build a trimmed graph starting from validate_input
    g = StateGraph(PaymentState)
    g.add_node("validate_input",  validate_input_node)
    g.add_node("format_error",    format_error_node)
    g.add_node("enrich_mcc",      enrich_mcc_node)
    g.add_node("call_odm",        call_odm_node)
    g.add_node("format_response", format_response_node)

    g.add_edge(START, "validate_input")
    g.add_conditional_edges("validate_input", _route_validation)
    g.add_edge("format_error",    END)
    g.add_edge("enrich_mcc",      "call_odm")
    g.add_edge("call_odm",        "format_response")
    g.add_edge("format_response", END)

    return g.compile().invoke(initial)
