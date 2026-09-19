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


