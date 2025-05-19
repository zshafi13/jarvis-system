import requests

def get_weather(location="Allentown"):
    try:
        response = requests.get(f"https://wttr.in/{location}?format=j1", timeout=5)
        data = response.json()

        current = data["current_condition"][0]
        temp_f = current["temp_F"]
        desc = current["weatherDesc"][0]["value"]

        return f"It’s currently {temp_f}°F and {desc.lower()} in {location}."

    except Exception as e:
        print(f"[Weather error] {e}")
        return "Sorry, I couldn’t fetch the weather right now."
