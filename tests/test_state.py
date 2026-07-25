from interface.state import GameState,Tile,Position,TileType,Color


def test_game_state_creation():
    state = GameState(
                    current_turn=1,
                    max_turn=20,
                    bunny = Position(x=0,y=0),
                    predators=[],
                    held_seed="none",
                    tiles=[
                        Tile(
                            pos=Position(x=0,y=0),
                            tile_type=TileType.PLANT,
                            color=Color.RED
                        ),
                        ]
                    )
    assert state.bunny.x == 0;
    assert len(state.predators) == 0;
    assert state.held_seed == "none";


