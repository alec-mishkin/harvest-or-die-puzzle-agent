import json
from interface.state import GameState

def test_load_unity_state():
    with open("tests/example_state.json") as f:
        data = json.load(f)
    print(data) 
    state = GameState.model_validate(data)

    assert state.current_turn == 1
    assert len(state.tiles) > 0
