import json, os
from openai import OpenAI
from pydantic import ValidationError

from interface.action import Turn
from interface.serialize import to_prompt

SYSTEM = """..."""   # same system prompt as before


class OpenRouterAgent:
    def __init__(self, model="anthropic/claude-sonnet-5", max_calls=200):
        self.model = model
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.environ["OPENROUTER_API_KEY"],
        )
        self.max_calls = max_calls
        self.calls = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.format_failures = 0
    
    def config(self):
        return {"model": self.model}

    def choose_turn(self, gs, candidates, error=None):
        if self.calls >= self.max_calls:
            raise RuntimeError(f"hit call cap ({self.max_calls})")

        
        content = to_prompt(gs)
        if error:
            content += f"\n\nYour previous choice was rejected: {error}\nChoose a different, legal move."

        resp = self.client.chat.completions.create(
            model=self.model,
            max_tokens=400,
            messages=[
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": content},
            ],
        
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "turn",
                "strict": True,
                "schema": Turn.model_json_schema(),
            },
        },
    )

    self.calls += 1
    if resp.usage:
        self.input_tokens += resp.usage.prompt_tokens
        self.output_tokens += resp.usage.completion_tokens

    raw = resp.choices[0].message.content
    try:
        return Turn.model_validate_json(raw)
    except ValidationError:
        self.format_failures += 1
        cleaned = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
        return Turn.model_validate_json(cleaned)   # let it raise on second failure



