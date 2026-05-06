# Debate System — Technical Specification (TZ) for a New Devin Session

> **Audience:** A fresh Devin session that will receive this document and build the system described below. The user (`@3mgeorgii`) wants to **parallelize technical-spec refinement** so the main Devin (working on Lilush implementation) is not the only source of design decisions.
>
> **Author:** Lilush main Devin session (https://app.devin.ai/sessions/03f8937522804560b6057ecb7e45c477)
>
> **Repository this targets:** https://github.com/3mgeorgii/pipeline
>
> **Status:** Specification only. Build is the new Devin's job.

---

## 0. TL;DR

Build a **two-agent debate system** ("спорящий котёл") where two LLMs from different providers **argue with each other** to refine a technical specification, then output a final consolidated design that the implementing Devin can build from.

The two agents:
- **Agent A** — a model from OpenAI (configurable, e.g. `gpt-5`, `gpt-5.5`, `o3-pro`, `gpt-4o` — whatever is current and accessible).
- **Agent B** — a model from Anthropic (configurable, e.g. `claude-sonnet-4.7`, `claude-sonnet-4.5`, `claude-opus-4.1` — whatever is current and accessible).

The model names "GPT-5.5" and "Claude 4.7" specifically requested by the user may not exist in the API yet. Make the system **fully model-agnostic** via env vars. The user picks the actual model strings at runtime.

---

## 1. Why this exists

The user's words:
> «я думаю было бы ошибкой складывать всю разработку на тебя. Я хочу чтобы ты подготовил технические задания для других devin... 2 иишки которые общаются друг с другом допилиывая технический пласт проект».

Translated: relying on a single Devin (with one underlying model) to design every refinement is risky. Different LLMs see different blind spots. Having two heterogeneous models **debate, critique, and refine** a spec catches more issues than a single-model design pass.

The output of the debate is a **better design document** that a regular implementation Devin (or human dev) can build from. The debate system itself does **not** write production code — it writes **refined specs**.

---

## 2. What you (the new Devin) must build

A standalone Python tool — call it **`debate-pot`** — that:

1. Reads a **topic file** (Markdown) describing the technical question to refine.
2. Spawns two LLM agents (one OpenAI, one Anthropic).
3. Runs a **multi-round debate protocol** (see §4).
4. Outputs a **final consolidated spec** ready for implementation.
5. Saves a **full transcript** of the debate so the user can audit the reasoning.

This tool can live **either**:
- **(A) As a sub-package inside the Lilush repo** at `bot/tools/debate.py`, exposed to the bot via a new command `/debate <topic-file-path>`. Recommended if the user wants to launch debates from Telegram.
- **(B) As a separate small repo / standalone CLI**. Recommended if you want it independent of Lilush. Simpler.

**Recommendation: (B)** — separate small repo `3mgeorgii/debate-pot` (or whatever the user prefers). Lilush is already complex; don't bloat it. The output of the debate (the refined spec markdown) gets manually committed into Lilush's `docs/` folder.

---

## 3. Lilush context (what the spec is being refined for)

Before you build, **read these in order**:

1. **`SAVE_STATE.md`** in the Lilush repo root — full project snapshot, architecture, all PRs, runtime layout.
2. **`docs/UNIQUEIZATION_SPEC.md`** in the Lilush repo — anti-detect editing pipeline spec (relevant to one of the debate topics).
3. **`bot/workers/seo.py`** — current SEO worker implementation (relevant to the other debate topic).
4. **`bot/workers/editor.py`** — current editor worker.
5. **`bot/workers/analyzer.py`** — current analyzer worker (helps you understand the data flow).

You don't need to modify Lilush itself. You need to understand it well enough to build a debate tool whose **output is implementable in Lilush**. The debate output is consumed by a **future** implementation Devin, not by you.

---

## 4. Debate protocol

The default protocol is **propose → critique → revise → judge**. Run as many rounds as needed for convergence, then synthesize.

### 4.1. Round structure

```
Round 1 (independent proposal):
    Agent A reads topic → proposes spec_A_1
    Agent B reads topic → proposes spec_B_1
    (Both work independently, no peeking.)

Round 2 (cross-critique):
    Agent A reads (topic + spec_A_1 + spec_B_1) → writes critique_A_of_B
    Agent B reads (topic + spec_B_1 + spec_A_1) → writes critique_B_of_A

Round 3 (revision):
    Agent A reads (topic + spec_A_1 + critique_B_of_A + spec_B_1)
        → writes spec_A_2 (revised)
    Agent B reads (topic + spec_B_1 + critique_A_of_B + spec_A_1)
        → writes spec_B_2 (revised)

Round 4+ (continue critique → revise loop until convergence)

Final round (synthesis):
    A "judge" model (third model, can be either provider, or a separate
    invocation of one of the agents in "neutral judge" mode)
    reads all rounds → produces final_spec.md
```

### 4.2. Convergence criteria

Stop the debate when one of the following happens:

1. **Stable rounds:** Both agents' latest proposals differ from their previous proposals by < 5% (compute via `difflib.SequenceMatcher.ratio()` or a Levenshtein-based metric). Two stable rounds in a row → converged.
2. **Hard cap:** `MAX_DEBATE_ROUNDS=6` (configurable). After 6 rounds, force synthesis even if not converged. Long debates rarely improve outcomes; you've extracted the model's best.
3. **Mutual agreement:** If both agents explicitly state in their critique "I agree with the other agent's proposal as-is", end early.

### 4.3. Judge model

The synthesizer can be:
- **Option 1:** A third model (e.g. `gpt-4o`, cheaper than the debate models) reads everything and writes the final spec.
- **Option 2:** One of the original agents in a **separate "neutral judge" invocation** — i.e., we wipe its agent identity, give it a fresh prompt: "You are a neutral senior architect. Read these two competing proposals and write the consolidated final spec."

**Recommendation: Option 2** with whichever provider has the cheapest model. Keeps the system to two API providers.

### 4.4. Prompt templates

Build these as **separate template files** under `prompts/` so the user can iterate on them without touching code. Suggested files:

- `prompts/system_propose.md` — system prompt for the initial proposal round
- `prompts/system_critique.md` — system prompt for the critique round
- `prompts/system_revise.md` — system prompt for the revision round
- `prompts/system_judge.md` — system prompt for the synthesis round

The user prompt for each round is the topic file + relevant prior content.

**Critical instructions to embed in the prompts:**

- "You are debating with another senior engineer from a competing company. Your job is to make the spec better, not to win the argument."
- "Cite specific lines/sections of the existing codebase or spec when critiquing."
- "Propose concrete code, env vars, and test plans — not vague principles."
- "If the other agent is right about something, say so explicitly. Don't argue for argument's sake."

This last point is essential — without it, LLM debates devolve into competitive nitpicking that produces worse output than a single-agent design.

### 4.5. Token budget

Each round is roughly: topic (5K tokens) + previous rounds (cumulative, growing). By round 6 the context could be 30-50K tokens per call. Both Anthropic and OpenAI flagship models support 200K+ context, so this is fine, but be aware of cost. Budget roughly:

- 6 rounds × 2 agents × ~30K input + ~5K output = ~12 LLM calls, ~$2-5 per debate at flagship pricing.

Add a `--dry-run` flag that estimates token cost before starting.

---

## 5. Output format

After the debate, produce a directory:

```
output/<debate-id>/
├── transcript.json      # Every prompt + every response, structured
├── transcript.md        # Human-readable transcript, agent A vs B side-by-side
├── final_spec.md        # The synthesized refined specification
├── debate_metadata.json # Models used, token counts, cost estimate, convergence stats
└── disagreements.md     # List of points the agents disagreed on with the
                         # judge's resolution — useful for the human to override
```

`final_spec.md` is the only file the user needs to commit into Lilush's `docs/`. The rest is for audit.

---

## 6. Configuration (env vars)

```bash
# API keys
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...

# Model selection (user overrides per debate)
DEBATE_MODEL_A=gpt-5            # OpenAI side; fallback: gpt-4o
DEBATE_MODEL_B=claude-sonnet-4.5  # Anthropic side; fallback: claude-3-5-sonnet-20241022
DEBATE_JUDGE_MODEL=gpt-4o-mini  # synthesis model; cheap

# Protocol tuning
MAX_DEBATE_ROUNDS=6
CONVERGENCE_DIFF_THRESHOLD=0.05   # stop if proposal change < 5%
TEMPERATURE=0.7                    # creativity for proposal/critique
JUDGE_TEMPERATURE=0.2              # low temp for synthesis (deterministic)

# Output
OUTPUT_DIR=./output                # where transcripts & final_spec land
```

---

## 7. CLI surface

```bash
debate-pot run --topic docs/DEBATE_TOPICS/seo-agent-v2.md
debate-pot run --topic docs/DEBATE_TOPICS/editor-agent-v2.md --max-rounds 4
debate-pot estimate --topic <path>          # dry-run cost estimate
debate-pot resume --debate-id <id>          # resume an interrupted debate
debate-pot transcript --debate-id <id>      # render transcript.md
```

Implement with `click` or `typer`. Don't reinvent CLI parsing.

---

## 8. Tech stack (recommended)

- **Language:** Python 3.12 (matches Lilush)
- **OpenAI SDK:** official `openai` package
- **Anthropic SDK:** official `anthropic` package
- **Async:** `asyncio` + `httpx` for parallel agent calls (round 1 proposals can run concurrently)
- **CLI:** `click` or `typer`
- **Diff:** `difflib` (stdlib) or `rapidfuzz` for convergence check
- **Optional:** `rich` for nice terminal output during debates

**Do NOT** use AutoGen, LangChain, LangGraph, or CrewAI for this. They're overkill, change frequently, and add 50MB of deps. The debate protocol described in §4 is ~300 lines of plain Python.

---

## 9. Test plan

1. **Mock-mode test:** A test mode that uses pre-recorded mock responses for both agents — verifies the round-robin protocol, convergence detection, output formatting **without** calling real APIs. Runs in CI.
2. **Smoke test (real API):** A tiny topic file ("design a function that adds two numbers — should it take ints or floats?") — runs ~2 rounds, costs $0.10, verifies real APIs work.
3. **Cost estimation accuracy:** Verify `debate-pot estimate` is within 20% of actual cost on the smoke test.
4. **Resume correctness:** Kill a debate mid-round-3, run `resume`, verify it picks up correctly.

CI config (GitHub Actions):
- Lint (`ruff`)
- Typecheck (`mypy --strict`)
- Mock-mode tests only (no real API calls in CI — too expensive, key leakage risk).

---

## 10. Integration with Lilush

The debate-pot **does not import Lilush** and **does not modify Lilush**. The only integration is:

1. The user (or implementing Devin) commits `final_spec.md` from `output/<debate-id>/` into Lilush's `docs/` folder, e.g. `docs/SEO_AGENT_V2_SPEC.md`.
2. A future implementation Devin reads that file and builds the actual code in Lilush.

Optional later enhancement (only if user explicitly wants):
- Add a `/debate <topic-name>` command to the Lilush bot that spawns a debate-pot subprocess. Out of scope for v1.

---

## 11. First two debate topics (provided)

Two topic files are committed alongside this TZ in the Lilush repo:

1. **`docs/DEBATE_TOPICS/seo-agent-v2.md`** — refine the SEO worker's design. Currently the SEO worker has known issues (template fallback is generic, language detection bug — Russian audio gets `defaultLanguage: en`, no per-platform tuning, no multi-variant generation). The debate should produce a refined spec for SEO v2.

2. **`docs/DEBATE_TOPICS/editor-agent-v2.md`** — refine the editor's uniqueization roadmap from `docs/UNIQUEIZATION_SPEC.md`. The current editor only does vertical crop. UNIQUEIZATION_SPEC proposes 9 future tentacles, but their order, parameter values, and parallelization strategy is unclear. The debate should produce a refined plan: which tentacles in what order, what specific values, what to parallelize, GPU vs CPU trade-offs, what can be skipped, what's MVP.

These are your **first runs**. The user will create more topic files in `docs/DEBATE_TOPICS/` over time.

---

## 12. Acceptance criteria

The new Devin's work is "done" when:

- [ ] `debate-pot` repo (or sub-package) is published with a green CI badge.
- [ ] `debate-pot run --topic docs/DEBATE_TOPICS/seo-agent-v2.md` produces a `final_spec.md` and `transcript.md`.
- [ ] `debate-pot run --topic docs/DEBATE_TOPICS/editor-agent-v2.md` produces the same.
- [ ] Both `final_spec.md` files are committed back into the Lilush repo as `docs/SEO_AGENT_V2_SPEC.md` and `docs/EDITOR_AGENT_V2_SPEC.md` via separate PRs.
- [ ] The user reviews the two final specs and gives a thumbs-up (or asks for re-debate with adjusted prompts).
- [ ] A short README in the debate-pot repo explains how to run a new debate end-to-end.

---

## 13. What this spec is NOT

- **Not** an implementation of the SEO v2 or editor v2 workers themselves. The debate produces specs; **implementation is a separate Devin's job**, after the user reviews the spec.
- **Not** a benchmark or eval framework. We're using debate to refine specs, not to compare model quality.
- **Not** a chat UI. CLI-only for v1. The user interacts with debate-pot via shell.
- **Not** integrated with the Lilush LLM brain (`bot/agent.py`). Lilush's brain is for chatting with the user; debate-pot is for refining engineering specs.

---

## 14. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Agents devolve into nitpicking | Prompt explicitly: "agree with the other when they're right" + low temperature for the judge synthesis. |
| Cost explosion on long topics | `--max-rounds 6` cap + `estimate` subcommand. |
| API outages mid-debate | `resume` subcommand persists state after each round. |
| Final spec contradicts existing Lilush architecture | The implementing Devin (next step) will catch this when it tries to build. The user reviews `final_spec.md` before commiting. |
| User asks for models that don't exist (e.g. "gpt-5.5") | Fallback chain: prefer the requested model, fall back to the latest available in that family. Log the actual model used in `debate_metadata.json`. |
| Heterogeneous SDK error handling | Wrap both OpenAI and Anthropic SDKs in a single `LLMClient` abstraction that normalizes errors, retries on rate limits with exponential backoff. |

---

## 15. Communication back to the user

The user (@3mgeorgii) speaks Russian primarily. They prefer:
- **Concise responses** (1-3 sentences default; longer only when explaining technical decisions).
- **Concrete next steps** (don't end messages with vague "let me know if you have questions").
- **Direct PR links** when work is done — don't restate what's in the PR description.
- **Suggesting saved secrets** when asking for API keys (so they're available in future sessions).

When you finish building the debate-pot, send the user:
1. PR link to the new repo.
2. One sample `final_spec.md` from one of the smoke debates so they see what the output looks like.
3. The two real debate outputs (SEO v2 + Editor v2) once they're ready.

---

## 16. How to start (literally, your first 30 minutes)

1. Read `SAVE_STATE.md`, `docs/UNIQUEIZATION_SPEC.md`, `bot/workers/seo.py`, `bot/workers/editor.py` in the Lilush repo. Take ~10 minutes.
2. Read this TZ end to end. ~5 minutes.
3. Read both topic files in `docs/DEBATE_TOPICS/`. ~5 minutes.
4. Decide: separate repo or sub-package? (recommended: separate repo)
5. Initialize the project: `pyproject.toml`, `pre-commit-config.yaml`, `.github/workflows/ci.yml` with ruff+mypy+pytest, basic Click CLI scaffold.
6. Implement the `LLMClient` abstraction first (200 lines, well-tested with mocks).
7. Implement the round protocol (300 lines).
8. Implement the synthesis step (100 lines).
9. Implement the CLI commands (200 lines).
10. Run a mock debate end-to-end. Then a real one on the cheapest models you have access to.
11. Commit final_specs back to Lilush as separate PRs.
12. Open a PR for the debate-pot repo and ping the user.

Total estimated effort: **2-3 days of focused Devin work**, parallelizable into child sessions for sub-tasks (CLI, LLMClient, prompt files, tests).

---

## 17. Notes for the user reading this

If you're @3mgeorgii reading this directly: this document is meant to be **handed to a new Devin session**. Concretely:

1. Open https://app.devin.ai/new
2. In the first message, paste the URL of this file (after merging the PR that creates it):
   `https://github.com/3mgeorgii/pipeline/blob/devin/init/docs/DEBATE_SYSTEM_TZ.md`
   along with: `Read this TZ and the linked Lilush context, then build the debate-pot tool described.`
3. The new Devin will need:
   - `OPENAI_API_KEY` (your OpenAI key — request it via Devin Secrets, save org-wide)
   - `ANTHROPIC_API_KEY` (your Anthropic key — same)
4. Approve the new Devin's PRs as they come in. Each one is small and reviewable.
5. Once the debate-pot is built, the new Devin will run the two smoke debates (SEO v2, Editor v2) and submit the resulting `final_spec.md` files as PRs to Lilush.
6. You review those final specs. If good, the **next** Devin (or the original Lilush Devin, i.e. me) implements them.

This way you have **3 parallel work streams**:
- Lilush main Devin (me) keeps building tentacles.
- Debate-pot Devin builds the debate tool.
- Implementation Devin (next session) implements the refined specs from debates.
