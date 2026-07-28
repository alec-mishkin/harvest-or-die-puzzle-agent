from pydantic import BaseModel, Field
from enum import StrEnum

class Direction(StrEnum):
    UP = "up"
    DOWN = "down"
    LEFT = "left"
    RIGHT = "right"

class Turn(BaseModel):
    """ One Turn: Harvest can be optionally chosen. A move must be chosen"""

    reasoning: str = Field(description="Brief plant for this turn")
    harvest: Direction | None = Field(
            default = None,
            description="Adjacent tile to harvest"
    )
    move: Direction = Field (description="Direction to step")
    @field_validator("harvest", "move", mode="before")
    @classmethod
    def _normalize_case(cls, v):
        return v.lower() if isinstance(v, str) else v
