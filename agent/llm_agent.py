from anthropic import Anthropic
from interface.action import Turn

SYSTEM = """You are playing Harvest or Die, a turn-based grid puzzle.

Each turn you may harvest one adjacent tile, then you MUST move one step.
Only the move consumes a turn; the harvest is free.

Harvesting a plant removes it and every connected plant of the same color,
leaving holes. Holes regrow after a few turns as the color you were holding
when you harvested. Your held seed becomes the color you just harvested.

You win when every scoring tile is the same color and no holes remain.
You lose if you run out of turns, step onto a hole, or touch a predator.

Think briefly, then commit to a harvest and a move."""

class LLMAgent:
    def __init__(self, model: str = "claude-sonnet-5", client: Anthropic | None = None):
        self.model = model
        self.client = client or Anthropic()

    def choose_turn(self, board: str, error: str | None = None) -> Turn:
        content = board
        if error:
            content += f"\n\nYour previous choice was rejected: {error}\nChoose a different, legal move."
        response = self.client.messages.parse(
                model=self.model,
                max_tokens=1024,
                system=SYSTEM,
                messages=[{"role": "user", "content": content}],
                output_format=Turn,
        )
        return response.parsed_output
