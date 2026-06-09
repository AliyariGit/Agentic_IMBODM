"""
Demo entry point — runs the payment authorization agent against test scenarios.

Prerequisites:
  1. Copy .env.example to .env and fill in your Azure OpenAI credentials
     (or set LLM_MODE=ollama and have Ollama running locally)
  2. Start the mock ODM server:
       uvicorn mock_odm_server:app --port 8080
  3. Run this file:
       python main.py
"""

from agent import build_agent

TEST_CASES = [
    # Happy path
    "I want to pay $4.50 at Java Joe Coffee Shop with my RBC Mastercard ending in 4532.",

    # NFC / contactless
    "Tap to pay $12.99 at Sobeys grocery store, card ending in 7890.",

    # Large amount — should trigger AmountLimitRule
    "Transfer $15,000 to a merchant in Toronto, card 4111111111111111.",

    # Restricted country — should trigger CountryBlacklistRule
    "Pay $200 USD at a hotel in Moscow, Russia. Card: 5500005555555559.",

    # Contactless over $250 — should trigger ContactlessLimitRule
    "Tap to pay $350 at Best Buy electronics. Card ending in 1234.",

    # Restricted MCC (gambling) — should trigger MCCRestrictionRule
    "I want to deposit $100 at an online casino (MCC 7995). Card: 4111111111111111.",
]


def main():
    print("=" * 60)
    print("  Agentic AI + IBM ODM — Payment Authorization Demo")
    print("=" * 60)

    agent = build_agent(verbose=False)

    for i, user_input in enumerate(TEST_CASES, 1):
        print(f"\n[Test {i}] {user_input}")
        print("-" * 60)
        result = agent.invoke({"input": user_input})
        print(result["output"])
        print()


if __name__ == "__main__":
    main()
