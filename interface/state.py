
from pydantic import BaseModel

Board = list[list[str]]

class GameState(BaseModel):
    """
        Current observable state of the Harvest or Die environment for AI agent.
    """
    turn : int
    turns_left: int
    board: Board
    available_actions: list[str]
