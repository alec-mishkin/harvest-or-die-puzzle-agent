from interface.state import GameState,Tile


def test_game_state_creation():
    state = GameState(
                    current_turn=1,
                    max_turn=20,
                    tiles=[
                        Tile(
                            x_pos=0,
                            y_pos=0,
                            bunny=False,
                            slime=False,
                            tile_type="blue_plant",
                        ),
                        Tile(
                            x_pos=1,
                            y_pos=0,
                            bunny=True,
                            slime=False,
                            tile_type="red_plant",
                        )
                        ],
                    )

    assert state.current_turn == 1
    assert state.tiles[0].bunny == False
