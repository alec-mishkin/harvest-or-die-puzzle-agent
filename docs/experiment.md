# Experimental write-up

Full methodology and results for the Harvest or Die LLM agent. The short version lives in the [README](../README.md).

All runs are recorded in [`results/runs.jsonl`](../results/runs.jsonl) with the git SHA of the code that produced them, the agent configuration, the seed range, and a `run_id` linking to per-turn transcripts under `results/transcripts/<run_id>/`.


---

## Contents

## Method

Each episode runs a single agent against a single level until it wins, dies, is cornered, or exhausts the turn limit. Every turn the harness:

1. converts the simulator state to a backend-agnostic `GameState`
2. renders it as an annotated ASCII prompt
3. enumerates all structurally legal turns and forward-simulates each one, marking which are fatal
4. asks the agent for a `Turn`
5. resolves it and records the outcome

Outcomes are mutually exclusive:

| Outcome | Meaning |
|---|---|
| `WIN` | every scoring tile the same colour, no holes remaining |
| `DEATH` | the agent chose a legal move that killed it |
| `CORNERED` | every legal move was fatal before the agent chose |
| `TIMEOUT` | survived to the turn limit without winning |
| `FORFEIT` | three consecutive structurally illegal moves |

### The inclusion of cornered
Cornered was included as an outcome to account for the case where the agent had no safe moves to go. This includes if they were surrounded by holes or surrounded by holes and predators. This became an important metri when investivate the results from the hard level. [Result 2](#result-2--deaths-on-the-hard-level-are-entrapment-not-bad-choices) exists entirely because this cornered was added; before it, the same data read as a 30% death rate for the greedy agent which is structurally incapable of dying by choice.

### Reproducibility
The random and greedy agents are seed and exactly reproducable. The LLM runs are not exactly reproducable because the reasoning models are nondeterministic even at fixed seetings. The LLM results are reported over N episodes. Every turn is persisted (the final prompt *as sent*, model reasoning, chosen action, outcome, latency, retry count) so any specific episode can be audited after the fact even though it cannot be regenerated.

Runs whose `git_sha` carries a `-dirty` suffix had uncommitted code changes and are not reproducible from a commit. `python -m agent.summarize --clean` filters to citable runs. Every figure quoted below comes from a clean commit.

## Agents
All agents implement one method, so baselines and LLM agents run through an identical episode loop and eval harness:

```python
def choose_turn(self, gs: GameState, candidates, error: str | None) -> Turn
```

**Random.** Uniform choice over structurally legal turns. Establishes the floor.

**Greedy.** Forward-simulates every legal turn one step, discards any that would be fatal, scores the remainder with the solver's admissible distance-to-goal bound (`min_blob_heuristic`), takes the minimum, breaks ties randomly with a seeded RNG.

**LLM.** `gpt-5.6-luna` through the OpenAI Responses API with structured outputs. The `Turn` Pydantic model is both the tool schema and the response validator, so malformed actions are impossible by construction and format failures are counted separately from bad play. The agent sees only the rendered text prompt. 

