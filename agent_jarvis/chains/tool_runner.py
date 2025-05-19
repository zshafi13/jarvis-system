from langchain.agents import Tool
from tools.weather import get_weather
from tools.news import get_news
from tools.stock import get_stock
from langchain_community.tools.tavily_search import TavilySearchResults
from dotenv import load_dotenv

load_dotenv()

# Create the Tavily tool instance
tavily_tool = TavilySearchResults(max_results=3)

# Create other tools that need wrapping
tools = [
    Tool(
        name="Get Weather",
        func=lambda location="Allentown": get_weather(location),
        description="Use to get the weather. Input should be the city name."
    ),
    Tool(
        name="Get Stock Price",
        func=lambda symbol="AAPL": get_stock(symbol),
        description="Use to get the stock price. Input should be a stock ticker symbol like TSLA or AAPL."
    ),
    Tool(
        name="Search Web",
        func=lambda query: tavily_tool.invoke({"query": query}),
        description="Use to search the web using Tavily. Input should be a search query string."
    )
]