from game.levels import make_sim

def test_run_experiment_writes_a_record(tmp_path, monkeypatch):
    import agent.experiment as exp
    monkeypatch.setattr(exp, "RESULTS", tmp_path / "runs.jsonl")
    monkeypatch.setattr(exp, "TRANSCRIPT_ROOT", tmp_path / "transcripts")

    sim = make_sim("level_3")
    record = exp.run_experiment(lambda s: RandomAgent(seed=s), sim, "level_3", episodes=2)

    assert record["episodes"] == 2
    assert sum(record["outcomes"].values()) == 2
    assert (tmp_path / "runs.jsonl").exists()
