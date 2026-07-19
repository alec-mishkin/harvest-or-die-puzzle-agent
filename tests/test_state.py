from interface.state import GameState


def test_game_state_creation():
    state = GameState(
                    turn=1,
                    turns_left=20,
                    board=[
                        ["blue_plant", "yellow_plant"],
                        ["bunny", "blue_plant"]],
                    available_actions=["move_up",
                                        "harvest"]
                    )

    assert state.turn == 1
    assert state.board[1][0] == "bunny"
