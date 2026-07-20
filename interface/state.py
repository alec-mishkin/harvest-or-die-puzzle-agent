
from pydantic import BaseModel

class Tile(BaseModel):
    """
        the state of the game board every turn
    """
    x_pos: int
    y_pos: int
    bunny: bool
    slime: bool
    tile_type: str


class GameState(BaseModel):
    """
        Current observable state of the Harvest or Die environment for AI agent.
    """
    current_turn : int
    max_turn: int
    tiles: list[Tile]
