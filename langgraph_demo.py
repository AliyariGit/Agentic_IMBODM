"""
LangGraph workflow demo — runs test cases and prints the execution path.

Modes:
  python langgraph_demo.py            # full LLM mode (needs Azure / Ollama)
  python langgraph_demo.py --no-llm   # skip LLM, supply structured fields directly
"""

import argparse
import sys
import io

# Force UTF-8 so checkmarks/crosses print on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from langgraph_workflow import run_workflow, run_workflow_from_fields

# ---------------------------------------------------------------------------
# Test cases for --no-llm mode (pre-extracted fields)
# ---------------------------------------------------------------------------
NO_LLM_CASES = [
    {
        "label": "Coffee Shop Tap — all rules pass",
        "fields": {
            "amount": 4.50, "card_number": "4532015112830366",
            "merchant_id": "java_joe_coffee", "mcc": "5812",
            "country": "CA", "entry_mode": "NFC_CONTACTLESS",
        },
    },
    {
        "label": "$15,000 → AmountLimitRule fires",
        "fields": {
            "amount": 15000, "card_number": "4111111111111111",
            "merchant_id": "merchant_toronto", "mcc": "5999",
            "country": "CA", "entry_mode": "CHIP",
        },
    },
    {
        "label": "Russia merchant → CountryBlacklistRule fires",
        "fields": {
            "amount": 200, "card_number": "5500005555555559",
            "merchant_id": "hotel_moscow", "mcc": "7011",
            "country": "RU", "entry_mode": "CHIP",
        },
    },
    {
        "label": "MCC 7995 gambling → MCCRestrictionRule fires",
        "fields": {
            "amount": 100, "card_number": "4111111111111111",
            "merchant_id": "online_casino", "mcc": "7995",
            "country": "CA", "entry_mode": "MANUAL",
        },
    },
    {
        "label": "Invalid card → CardValidityRule fires",
        "fields": {
            "amount": 50, "card_number": "1234567890123456",
            "merchant_id": "shop_retail", "mcc": "5311",
            "country": "CA", "entry_mode": "CHIP",
        },
    },
    {
        "label": "Contactless $350 → ContactlessLimitRule fires",
        "fields": {
            "amount": 350, "card_number": "4532015112830366",
            "merchant_id": "best_buy_electronics", "mcc": "5732",
            "country": "CA", "entry_mode": "NFC_CONTACTLESS",
        },
    },
    {
        "label": "Missing MCC → enrich_mcc infers from merchant name",
        "fields": {
            "amount": 12.99, "card_number": "5500005555555559",
            "merchant_id": "sobeys_grocery_store", "mcc": None,
            "country": "CA", "entry_mode": "CHIP",
        },
    },
    {
        "label": "Validation error — zero amount",
        "fields": {
            "amount": 0, "card_number": "4532015112830366",
            "merchant_id": "some_shop", "mcc": "5999",
            "country": "CA", "entry_mode": "CHIP",
        },
    },
]

# Full NL cases (needs LLM)
NL_CASES = [
    "I want to pay $4.50 at Java Joe Coffee Shop with my RBC Mastercard ending in 4532.",
    "Transfer $15,000 to a Toronto merchant using card 4111111111111111.",
    "Please charge $200 to my card at the hotel in Moscow, Russia. Card: 5500005555555559.",
    "Tap to pay $350 at Best Buy with my Visa ending in 0366.",
    "What's my balance?",   # missing fields — should request clarification
]


def _decision_icon(answer: str) -> str:
    if "approved" in answer.lower():
        return "✓"
    if "declined" in answer.lower():
        return "✗"
    if "details" in answer.lower() or "provide" in answer.lower():
        return "?"
    return "!"


def _render_trace(trace: list[str]) -> str:
    return " → ".join(f"[{n}]" for n in trace)


def run_no_llm():
    print("\n" + "=" * 68)
    print("  LangGraph Workflow — Pre-extracted Fields Mode (no LLM)")
    print("=" * 68)

    for i, case in enumerate(NO_LLM_CASES, 1):
        result = run_workflow_from_fields(case["fields"])
        icon = _decision_icon(result["final_answer"])
        odm = result.get("odm_response") or {}
        inferred_mcc = result["extracted"].get("mcc", "?")

        print(f"\n[{i}] {case['label']}")
        print(f"    {icon} {result['final_answer']}")
        print(f"    Path : {_render_trace(result['step_trace'])}")
        if odm.get("authorizationCode"):
            print(f"    Auth : {odm['authorizationCode']}")
        if odm.get("declineReason"):
            print(f"    Rule : {next((t['ruleName'] for t in odm.get('auditTrail',[]) if t.get('fired')), '-')}")
        if case["fields"].get("mcc") is None:
            print(f"    MCC  : inferred → {inferred_mcc}")


def run_llm():
    print("\n" + "=" * 68)
    print("  LangGraph Workflow — Full NL Mode (LLM + IBM ODM)")
    print("=" * 68)

    for i, message in enumerate(NL_CASES, 1):
        print(f"\n[{i}] User: {message}")
        result = run_workflow(message)
        icon = _decision_icon(result["final_answer"])
        print(f"    {icon} Agent: {result['final_answer']}")
        print(f"    Path : {_render_trace(result['step_trace'])}")
        if result.get("extracted"):
            e = result["extracted"]
            print(f"    Extr : amount={e.get('amount')}  mcc={e.get('mcc')}  country={e.get('country')}")


def main():
    parser = argparse.ArgumentParser(description="LangGraph workflow demo")
    parser.add_argument("--no-llm", action="store_true",
                        help="Use pre-extracted fields (no Azure / Ollama needed)")
    args = parser.parse_args()

    if args.no_llm:
        run_no_llm()
    else:
        run_llm()

    print("\n" + "=" * 68)


if __name__ == "__main__":
    main()
