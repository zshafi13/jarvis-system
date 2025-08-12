# stock.py
***
## get_stock Method

The `get_stock` method retrieves the latest stock data for a given symbol using the Yahoo Finance API. It provides information about the stock's closing price, the change in price from the opening, and the percentage change, along with the direction of the change.

### Parameters

- `symbol`: *(str, optional)*  
  The stock symbol for which data is to be fetched. Defaults to `"TSLA"`. The symbol is first converted to lowercase and then mapped to its corresponding value using `symbol_map`. If no mapping is found, it is converted to uppercase.

### Returns

- *(str)*  
  A formatted string containing the stock symbol in uppercase, the latest closing price, the direction of the price change (up, down, or unchanged), and the percentage change in price.

### Exceptions

- If an error occurs during the fetching of stock data, an exception is caught, and a message "Couldn't fetch stock data right now, sir." is returned.
***
## Scripted Content Summary

- The program contains a dictionary named `symbol_map`.
- This dictionary maps company names to their respective stock symbols.
- Companies included in the dictionary are major technology and entertainment firms such as Tesla, Apple, Microsoft, Nvidia, Google, Meta, Amazon, Netflix, Intel, PayPal, AMD, and Qualcomm.
- Some companies have multiple names mapping to the same stock symbol, such as Google and Alphabet both mapping to "GOOG", and Meta and Facebook both mapping to "META".

***
###### _Powered by Code Intelligence | DocGen_
