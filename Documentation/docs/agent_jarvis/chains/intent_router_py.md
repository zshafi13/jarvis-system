# intent_router.py
***
## Scripted Content Summary

- **Intent Classification for Voice Assistant**: The script is designed to classify user intents for a voice assistant named Jarvis. It processes natural language inputs to determine user requests.

- **Available Intents**:
  - **get_weather**: Identifies requests for weather information, extracting a location.
  - **get_stock**: Detects inquiries about stock information, extracting a stock symbol like TSLA, AAPL, or MSFT.
  - **search_web**: Recognizes requests for general or up-to-date information, extracting a query for news, updates, or factual queries.
  - **freeform**: Serves as a fallback for small talk or unclear requests not covered by other intents.

- **Context Utilization**: The script uses context from previous interactions to interpret follow-up questions, ensuring continuity in conversation.

- **Response Format**: The output is structured as a JSON object specifying the intent and relevant parameters.

- **Example Scenarios**: Provides examples of user queries and the corresponding intent classification, demonstrating how the system extracts necessary information.

- **Integration**: The classification prompt is combined with the `Ollama` model to form a `router_chain`, facilitating the processing of user inputs through the defined intents.

***
###### _Powered by Code Intelligence | DocGen_
