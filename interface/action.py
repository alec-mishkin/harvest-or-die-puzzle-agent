from pydantic import BaseModel
from typing import Any

class Action(BaseModel):
    action_type: str
    parameters: dict[str, Any]
