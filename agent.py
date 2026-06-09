"""
LangChain agent wiring.

Supports two LLM backends controlled by LLM_MODE env var:
  - "azure"  → Azure OpenAI GPT-4 (cloud, high accuracy)
  - "ollama" → Phi-3 via Ollama (local, zero cost, lower latency)
"""

import os
from dotenv import load_dotenv
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.agents import AgentExecutor, create_openai_tools_agent
from odm_tool import authorize_payment

load_dotenv()

# ---------------------------------------------------------------------------
# MCC reference — helps the LLM map merchant names to ISO codes
# ---------------------------------------------------------------------------
MCC_HINTS = """
Common MCC codes:
- 5812 = Restaurants / food service (coffee shops, fast food, sit-down)
- 5411 = Grocery stores / supermarkets
- 5541 = Gas stations / petrol
- 5732 = Electronics stores
- 5912 = Drug stores / pharmacies
- 5311 = Department stores
- 5999 = Miscellaneous retail
- 7011 = Hotels / lodging
- 4111 = Transportation / transit
- 7995 = Gambling / betting (RESTRICTED)
- 9754 = Lottery (RESTRICTED)
"""

SYSTEM_PROMPT = f"""You are a payment authorization assistant for a Canadian bank.

When a user wants to make a payment, your job is to:
1. Extract the transaction amount, merchant name, and card details from their message
2. Determine the merchant's ISO 18245 MCC code based on the merchant name/type
3. Determine the country (default to 'CA' if not mentioned)
4. Determine the entry mode (default to 'CHIP'; use NFC_CONTACTLESS if they say tap/contactless)
5. If only the last 4 digits of a card are given, pad to 16 digits: 000000000000<last4>
6. Call the authorize_payment tool with all extracted fields
7. Explain the decision in clear, friendly language

{MCC_HINTS}

Always include the authorization code when approved, or the specific reason when declined.
Never make up an authorization decision — always use the authorize_payment tool.
"""


def build_agent(verbose: bool = True) -> AgentExecutor:
    llm_mode = os.getenv("LLM_MODE", "azure").lower()

    if llm_mode == "ollama":
        from langchain_community.chat_models import ChatOllama
        llm = ChatOllama(
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            model=os.getenv("OLLAMA_MODEL", "phi3"),
            temperature=0,
        )
    else:
        from langchain_openai import AzureChatOpenAI
        llm = AzureChatOpenAI(
            azure_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4"),
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01"),
            temperature=0,
        )

    tools = [authorize_payment]

    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        MessagesPlaceholder("chat_history", optional=True),
        ("human", "{input}"),
        MessagesPlaceholder("agent_scratchpad"),
    ])

    agent = create_openai_tools_agent(llm, tools, prompt)
    return AgentExecutor(agent=agent, tools=tools, verbose=verbose)
