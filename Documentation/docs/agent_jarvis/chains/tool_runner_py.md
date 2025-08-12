# tool_runner.py
***
## Scripted Content Summary

- The script utilizes the `load_dotenv()` function, which suggests it loads environment variables from a `.env` file.
- A `TavilySearchResults` object is instantiated with a maximum of 3 results, indicating a web search functionality.
- The script defines a list of tools, each represented by a `Tool` object:
  - **Get Weather**: 
    - Function: `get_weather(location)`
    - Description: Fetches weather information for a specified city. Defaults to "Allentown".
    - [Documentation](../tools/weather.md)
  - **Get Stock Price**: 
    - Function: `get_stock(symbol)`
    - Description: Retrieves the stock price for a given ticker symbol. Defaults to "AAPL".
    - [Documentation](../tools/stock.md)
  - **Search Web**: 
    - Function: Uses `tavily_tool.invoke` to perform a web search.
    - Description: Executes a web search using Tavily with a provided query string.

***
###### _Powered by Code Intelligence | DocGen_
