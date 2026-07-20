import json
from interface.state import GameState

def test_load_unity_state():
    with open("tests/example_state.json") as f:
        data = json.load(f)
    
    state = GameState(**data)

    assert state.current_turn == 1
    assert len(state.board_states) > 0

    bunny_tiles = [tile for tile in state.board_states if tile.bunny]

    assert len(bunny_tiles) == 1
