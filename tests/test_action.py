from interface.action import Action

def test_action_creation():
    action = Action(
            action_type="move",
            parameters={
                "direction":"up"
            }
    )
    assert action.action_type == "move"
    assert action.parameters["direction"] == "up"
