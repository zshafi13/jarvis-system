# intent_router.py
***
## Scripted Content Summary

- The script initializes an instance of the `Ollama` class with a model named "llama3.2".
- A `ChatPromptTemplate` is created for classifying user intents for a voice assistant named Jarvis.
- The classification prompt defines four possible intents:
  - **get_weather**: Extracts a "location" for weather information.
  - **get_stock**: Extracts a "symbol" for stock information.
  - **search_web**: Extracts a "query" for general or up-to-date information.
  - **freeform**: Used as a fallback for unclear or small talk messages.
- The prompt uses a "context" from the last interaction to interpret follow-up queries.
- The expected response format is a JSON object indicating the intent and parameters.
- Examples are provided to illustrate how to classify different user inputs.
- The `router_chain` is created by combining the `classification_prompt` with the `llm` instance.

***
###### _Powered by Code Intelligence | DocGen_
