from langchain.prompts import ChatPromptTemplate
from langchain_community.llms import Ollama

llm = Ollama(model="llama3.2")

classification_prompt = ChatPromptTemplate.from_messages([
    ("human", """You are a smart intent classifier for a voice assistant named Jarvis.

Your task is to take a natural language input and determine what the user wants.

Available **intents**:
- get_weather: The user wants weather information. You must extract a \"location\".
- get_stock: The user is asking about a company’s stock. You must extract a \"symbol\" like TSLA, AAPL, MSFT.
- search_web: The user wants general or up-to-date information. This includes news, updates, headlines, or any open-ended factual queries. You must extract a \"query\".
- freeform: The message is small talk, unclear, or not covered above. Use only as a fallback.

You will also receive a \"context\" from the last interaction. Use it to interpret follow-ups like \"what about that?\" or \"is there any news on it?\"

Respond ONLY with a JSON object like:
{{
  \"intent\": \"search_web\",
  \"parameters\": {{
    \"query\": \"latest news about Microsoft stock\"
  }}
}}

Examples:

User: \"how's Tesla stock doing?\"
→ get_stock, symbol: TSLA

User: \"what's the weather in Paris?\"
→ get_weather, location: Paris

User: \"get me the latest news\"
→ search_web, query: \"latest news\"

User: \"is there anything in the news about that?\"
→ Use the context to determine what \"that\" refers to. If unclear, use search_web with a vague query.

Now classify:
\"{input}\"

Context:
\"{context}\"
""")
])

router_chain = classification_prompt | llm
