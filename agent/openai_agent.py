from dotenv import load_dotenv
from openai import OpenAI
from interface.action import Turn
from interface.serializer import to_prompt
from interface.annotations import futile_harvests 
from agent.prompts import SYSTEM_V1

load_dotenv()

SYSTEM = SYSTEM_V1   # same system prompt

class OpenAIAgent:
    def __init__(self, model="gpt-5.6-luna", max_calls=200,
                 prompt_version="v1", show_fatal=False, show_futile=False):
        self.model = model
        self.prompt_version = prompt_version
        self.show_fatal = show_fatal
        self.show_futile = show_futile
        self.client = OpenAI()          # reads OPENAI_API_KEY from env
        self.max_calls = max_calls
        self.calls = 0
        self.input_tokens = 0
        self.output_tokens = 0


    def config(self):
        return {
                "model": self.model,
                "prompt_version": self.prompt_version,
                "show_fatal": self.show_fatal,
                "show_futile": self.show_futile,
        }

    def choose_turn(self, gs, candidates, error=None):
        if self.calls >= self.max_calls:
            raise RuntimeError(f"hit call cap ({self.max_calls})")
        
        content = to_prompt(gs)

        if self.show_fatal:
            fatal = [t for t, s in candidates if s is None]
            if fatal:
                lines = [f"- harvest {t.harvest or 'none'}, move {t.move}" for t in fatal]
                content += "\n\nFATAL this turn — these legal moves would kill you:\n" + "\n".join(lines)
        
        if self.show_futile:
            fut = futile_harvests(gs)
            if fut:
                dirs = ", ".join(d.value for d in fut)
                content += (f"\n\nPOINTLESS this turn: harvesting {dirs} targets a "
                            f"{gs.held_seed.upper()} plant while you hold {gs.held_seed.upper()}. "
                            f"Those tiles would regrow the same colour and your seed would not "
                            f"change — the board ends up unaltered, with the tiles sitting as "
                            f"holes for two turns. To convert a region, hold the colour you want "
                            f"and harvest a colour you are NOT holding.")

        if error:
            content += f"\n\nYour previous choice was rejected: {error}\nChoose a different, legal move."
        
        self.last_prompt = content        # after all annotations are appended
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

