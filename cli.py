"""
Interactive CLI — chat with the payment authorization agent.

Usage:
    python cli.py
    python cli.py --no-llm    # test ODM directly without the LLM agent
"""

import argparse
import json
import requests
import sys

ODM_URL = "http://localhost:8080"


def check_odm_health() -> bool:
    try:
        r = requests.get(f"{ODM_URL}/health", timeout=2)
        return r.status_code == 200
    except requests.exceptions.ConnectionError:
        return False


def run_agent_cli():
    from agent import build_agent
    agent = build_agent(verbose=False)
    history = []

    print("\nPayment Authorization Agent (type 'quit' to exit)\n")
    print("Example: 'Pay $4.50 at Java Joe coffee shop, card ending in 4532'\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break

        if user_input.lower() in {"quit", "exit", "q"}:
            print("Goodbye.")
            break
        if not user_input:
            continue

        result = agent.invoke({"input": user_input, "chat_history": history})
        print(f"\nAgent: {result['output']}\n")

        history.append(("human", user_input))
        history.append(("assistant", result["output"]))


def run_direct_odm():
    """Bypass the LLM — send JSON directly to the mock ODM server."""
    print("\nDirect ODM Test Mode (no LLM)\n")
    print("Enter a JSON payload or press Enter for a sample transaction.\n")

    sample = {
        "transactionAmount": 4.50,
        "cardNumber": "4532015112830366",
        "merchantId": "java_joe_001",
        "mcc": "5812",
        "country": "CA",
        "entryMode": "NFC_CONTACTLESS"
    }

    raw = input(f"Payload [{json.dumps(sample)}]: ").strip()
    payload = json.loads(raw) if raw else sample

    try:
        r = requests.post(f"{ODM_URL}/api/authorize", json=payload, timeout=5)
        result = r.json()
        print("\n--- ODM Response ---")
        print(json.dumps(result, indent=2))
    except requests.exceptions.ConnectionError:
        print(f"\nERROR: Cannot reach ODM server at {ODM_URL}")
        print("Run: uvicorn mock_odm_server:app --port 8080")


def main():
    parser = argparse.ArgumentParser(description="Payment Authorization Agent CLI")
    parser.add_argument("--no-llm", action="store_true",
                        help="Test ODM directly without the LLM agent")
    args = parser.parse_args()

    if not check_odm_health():
        print(f"WARNING: ODM server not reachable at {ODM_URL}")
        print("Start it with: uvicorn mock_odm_server:app --port 8080\n")
        if args.no_llm:
            sys.exit(1)

    if args.no_llm:
        run_direct_odm()
    else:
        run_agent_cli()


if __name__ == "__main__":
    main()
