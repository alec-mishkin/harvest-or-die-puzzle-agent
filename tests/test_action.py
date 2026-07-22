import pytest
from pydantic import ValidationError
from interface.action import Turn, Direction

def test_action_creation():
    action_turn = Turn(
            reasoning =  "Need the blue plant",
            harvest="up",
            move="left"
    )
    assert action_turn.harvest == Direction.UP
    assert action_turn.move == Direction.LEFT

def test_harvest_defaults_to_none():
    turn = Turn(reasoning="Need to move up", move="up")
    assert turn.harvest is None

def test_invalid_direction_raises():
    with pytest.raises(ValidationError):
        Turn(reasoning="bad move", move ="diagonal")

def test_move_is_required():
    with pytest.raises(ValidationError):
        Turn(reasoning="no move give", harvest="up")
