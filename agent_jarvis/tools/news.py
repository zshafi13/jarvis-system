import feedparser

def get_news():
    try:
        feed = feedparser.parse("https://www.reddit.com/r/news/.rss")
        if feed.entries:
            return f"Here’s a headline: {feed.entries[0].title}"
        return "No news headlines at the moment."
    except Exception:
        return "Couldn’t fetch the news."
