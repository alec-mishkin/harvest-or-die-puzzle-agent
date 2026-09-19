from game.levels import make_sim
from agent.play import play_episode
def test_random_agent_runs_a_full_episode():
    sim = make_sim("level_3")
    result, history = play_episode(RandomAgent(seed=0), sim, verbose=False)
    assert result in {"WIN", "DEATH", "CORNERED", "TIMEOUT", "FORFEIT"}
    assert history


def test_greedy_agent_runs_a_full_episode():
    sim = make_sim("level_3")
    result, _ = play_episode(GreedyAgent(sim, seed=0), sim, verbose=False)
    assert result in {"WIN", "DEATH", "CORNERED", "TIMEOUT", "FORFEIT"}
