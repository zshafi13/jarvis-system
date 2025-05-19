# agent_state.py
# A centralized place to store session state and enable multi-step reasoning

class AgentState:
    def __init__(self):
        self.last_tool_result = None
        self.last_intent = None
        self.last_parameters = None

    def update(self, intent: str, parameters: dict, result: str):
        self.last_intent = intent
        self.last_parameters = parameters
        self.last_tool_result = result

    def get_context(self):
        return {
            "last_intent": self.last_intent,
            "last_parameters": self.last_parameters,
            "last_tool_result": self.last_tool_result
        }

# Create a global instance
agent_state = AgentState()
