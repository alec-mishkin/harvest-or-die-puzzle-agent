from dotenv import load_dotenv
from openai import OpenAI
from interface.action import Turn
from interface.serializer import to_prompt
from agent.prompts import SYSTEM_V1

load_dotenv()

SYSTEM = SYSTEM_V1   # same system prompt

class OpenAIAgent:
    def __init__(self, model="gpt-5.6-luna", max_calls=200):
        self.model = model
        self.client = OpenAI()          # reads OPENAI_API_KEY from env
        self.max_calls = max_calls
        self.calls = 0
        self.input_tokens = 0
        self.output_tokens = 0

    def config(self):
        return {"model": self.model}

    def choose_turn(self, gs, candidates, error=None):
        if self.calls >= self.max_calls:
            raise RuntimeError(f"hit call cap ({self.max_calls})")
        
        content = to_prompt(gs)
        if error:
            content += f"\n\nYour previous choice was rejected: {error}\nChoose a different, legal move."

        response = self.client.responses.parse(
            model=self.model,
            input=[
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": content},
            ],
            text_format=Turn,
        )

        self.calls += 1
        if response.usage:
            self.input_tokens += response.usage.input_tokens
            self.output_tokens += response.usage.output_tokens

        return response.output_parsed

