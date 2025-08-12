# tool_runner.py
***
## Scripted Content Summary

- **Environment Setup**: Utilizes `load_dotenv()` to load environment variables from a `.env` file, which is typically used for configuration purposes.

- **Tool Definitions**:
  - **Get Weather Tool**: 
    - Function: `get_weather(location)`
    - Description: Fetches weather information for a specified city. Defaults to "Allentown" if no city is provided.
    - Usage: Returns the current temperature and weather description.
    - [Documentation](../tools/weather.md)
  
  - **Get Stock Price Tool**:
    - Function: `get_stock(symbol)`
    - Description: Retrieves the current stock price and percentage change for a given stock ticker symbol. Defaults to "AAPL" if no symbol is provided.
    - Usage: Provides stock price, direction of change, and percentage change.
    - [Documentation](../tools/stock.md)
  
  - **Search Web Tool**:
    - Function: `tavily_tool.invoke({"query": query})`
    - Description: Performs a web search using Tavily. Requires a search query string as input.
    - Usage: Returns search results based on the query.

- **Error Handling**: Each tool includes error handling to manage exceptions and provide user-friendly error messages when data cannot be fetched.

***
###### _Powered by Code Intelligence | DocGen_
