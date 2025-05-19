import json
import re  #for cleaning bad JSON
from chains.intent_router import router_chain
from chains.tool_runner import tools
from langchain_community.llms import Ollama
from langchain.memory import ConversationBufferMemory
from chains.agent_state import agent_state

import time

# Initialize your freeform fallback LLM
freeform_llm = Ollama(model="llama3.2")

# Tool registry
tool_map = {
    "get_weather": tools[0].func,
    "get_stock": tools[1].func,
    "search_web": tools[2].func
}

# Handle unclassified, casual, or chatty messages
def run_freeform_response(text: str) -> str:
    context = agent_state.get_context()
    use_context = is_followup(text)

    context_prompt = ""
    if use_context and context["last_intent"] and context["last_tool_result"]:
        context_prompt = (
            f"\n\nThe user previously asked for: \"{context['last_intent']}\" "
            f"with parameters: {context['last_parameters']}, and your last response was:\n"
            f"{context['last_tool_result']}\n"
            f"This new message is likely a follow-up."
        )

    prompt = (
        f"You are Jarvis, a witty, charming AI modeled after the JARVIS in Marvel. "
        f"You're speaking aloud through a voice assistant made by Mr. Shafi. "
        f"Keep responses under 500 characters. Be helpful, clever, and slightly sarcastic unless it's a serious tone.\n"
        f"{context_prompt}\n\n"
        f"The user said: \"{text}\"\n"
        f"Respond appropriately. If they asked for a joke, tell one. If they greeted you, greet back. "
        f"If it’s vague, say something witty or ask a clarifying question. Speak as if you're talking out loud."
    )

    return freeform_llm.invoke(prompt).strip()

def run_search_summary(results: list, query: str) -> str:
    content_summary = "\n\n".join([
        f"Article {i+1}:\nTitle: {r.get('title', '')}\nContent: {r.get('content', '')}"
        for i, r in enumerate(results[:3])
    ])

    prompt = (
        f"You are Jarvis, an intelligent assistant modeled after the JARVIS AI in the Marvel Cinematic Universe, created by Mr. Shafi. "
        f"The user asked you to search the web for: \"{query}\".\n\n"
        f"Here are a few articles you found:\n{content_summary}\n\n"
        f"Based on this, generate a brief spoken response (under 500 characters) summarizing the key takeaways, "
        f"adding your signature charm, sarcasm, or wit. Do not include URLs. Just talk to the user as if you're speaking aloud."
    )

    return freeform_llm.invoke(prompt).strip()


def run_agent(user_input: str) -> str:
    try:
        # Step 1: Classify intent using LangChain invoke
        router_output = router_chain.invoke({
            "input": user_input,
            "context": str(agent_state.get_context())
        })
        router_result = router_output
        print("[Router RAW Output]:", router_result)

        # Step 2: Clean and parse the result
        cleaned = re.sub(r"```json|```", "", router_result).strip()
        first_brace = cleaned.find("{")
        if first_brace != -1:
            cleaned = cleaned[first_brace:]
        cleaned = cleaned.replace("\\'", "'")
        print("[Cleaned JSON Candidate]:", cleaned)

        parsed = json.loads(cleaned)
        intent = parsed["intent"]
        params = parsed.get("parameters") or {}

        # Step 3: Handle intents
        if intent == "freeform":
            return run_freeform_response(params.get("query", ""))

        if intent == "search_web":
            result = tool_map["search_web"]
            raw_results = result(params.get("query", ""))
            summary = run_search_summary(raw_results, params.get("query", ""))
            agent_state.update(intent, params, summary)
            return summary

        tool = tool_map.get(intent)
        if not tool:
            return "Sorry, I don't know how to handle that command yet."

        result = tool(**params) if params else tool()
        agent_state.update(intent, params, result)
        return result

    except json.JSONDecodeError as e:
        print("[Parse error] Raw router output:", router_result)
        print(f"[ERROR] Failed to parse JSON: {e}")
        return "Sorry, I couldn’t understand that command."
    except Exception as e:
        print("[ERROR]:", e)
        return "Sorry, something went wrong."
    
def is_followup(new_input: str) -> bool:
    context = agent_state.get_context()
    last_summary = f"Intent: {context['last_intent']}, Parameters: {context['last_parameters']}, Response: {context['last_tool_result']}"

    prompt = (
        f"You are a classifier. Determine if the user input is a follow-up to the previous exchange.\n\n"
        f"Previous interaction:\n{last_summary}\n\n"
        f"New user input:\n{new_input}\n\n"
        f"Reply with only 'yes' or 'no'."
    )

    response = freeform_llm.invoke(prompt).strip().lower()
    return response.startswith("y")
    