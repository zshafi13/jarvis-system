from flask import Flask, request, jsonify
from agent import run_agent
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

@app.route("/jarvis", methods=["POST"])
def jarvis_route():
    try:
        data = request.json
        user_input = data.get("input", "")
        if not user_input:
            return jsonify({"error": "No input provided"}), 400

        print(f"[JARVIS RECEIVED]: {user_input}")
        response = run_agent(user_input)

        return jsonify({"response": response})

    except Exception as e:
        print("[SERVER ERROR]:", e)
        return jsonify({"error": "Server error"}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=11434)
