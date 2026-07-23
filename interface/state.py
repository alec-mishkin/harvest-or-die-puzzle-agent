
from pydantic import BaseModel
from enum import StrEnum

class Color(StrEnum):
    RED = "red"
    BLUE = "blue"
    YELLOW = "yellow"
    PURPLE = "purple"
    NONE = "none"

class TileType(StrEnum):
    PLANT = "plant"
    BUSH = "bush"
    HOLE = "hole"
    GROUND = "ground"
    WALL = "wall"
    SPWAN = "spawn"
    DIAGONAL_SPAWN = "diagonal_spawn"

class Position(BaseModel):
    x: int
    y: int

class Predator(BaseModel):
    pos: Position
    next_pos: Position | None #Telegraphed target for next turn
    diagnoal: bool #Whether or not the predator will move in a diagonal or cartesian methodology


class Tile(BaseModel):
    """
        the state of the game board every turn
    """
    pos: Position
    tile_type: TileType #enum (plant, bush, hole, ground)
    color: Color #enum: (red/blue/yellow/purple/none)
    hole_counter: int | None = None 
    scored: bool = True 


class GameState(BaseModel):
    """
        Current observable state of the Harvest or Die environment for AI agent.
    """
    current_turn : int
    max_turn: int
    bunny: Position
    held_seed: Color
    tiles: list[Tile]
    predators: list[Predator]
