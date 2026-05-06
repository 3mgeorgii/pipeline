# Parallel Devins — How to use

This folder contains **3 prompt files** you can copy-paste into 3 separate Devin sessions to parallelize work on Lilush.

## The pipeline

```
                ┌─── Devin 1 (Claude Opus 4.7) ────┐
Topic file ────►│                                   ├──► final_spec.md ──► Devin 3 ──► Working tool ──► You ──► Main Devin (Lilush integration)
                └─── Devin 2 (ChatGPT 5.5) ────────┘                       (impl)        (in repo)              (this session)
                  ↑ they argue in a shared GitHub repo
```

- **Devin 1 + Devin 2** debate in a shared repo and produce one refined Technical Specification (TZ).
- **Devin 3** reads the TZ and implements the actual tool. Uses a code-review sub-agent loop until quality is 9/10.
- **You** take Devin 3's working tool and hand it to the Lilush main Devin (this session) for integration into the bot.

## How to launch

### Step 1 — Pick a topic

You currently have two topic files ready:

- `docs/DEBATE_TOPICS/seo-agent-v2.md` — refine the SEO worker
- `docs/DEBATE_TOPICS/editor-agent-v2.md` — refine the editor / uniqueization pipeline

Pick **one**. Don't run both topics through the same Devin 1 / Devin 2 — start one engagement at a time, get used to the workflow, then run more in parallel later.

### Step 2 — Launch Devin 1 (Opus)

1. Open https://app.devin.ai/new from your **Devin 1 account** (one Devin account, separate from your main one).
2. In the model picker, select **Claude Opus 4.7** (or whatever the latest Opus is).
3. Open `docs/PARALLEL_DEVINS/DEVIN1_PROMPT.md`. Copy everything below the `---` line.
4. Replace `<TOPIC_FILE_URL>` with one of the two topic file URLs (e.g. `https://github.com/3mgeorgii/pipeline/blob/devin/init/docs/DEBATE_TOPICS/seo-agent-v2.md`).
5. Paste into Devin 1's first message. Send.
6. Wait. Devin 1 will create a new GitHub repo (e.g. `3mgeorgii/lilush-tz-debate-seo-agent-v2`) and report the URL back to you.

### Step 3 — Launch Devin 2 (GPT)

1. Open https://app.devin.ai/new from your **Devin 2 account** (a different Devin account from Devin 1).
2. In the model picker, select **ChatGPT 5.5** (or whatever the latest GPT-5 family is).
3. Open `docs/PARALLEL_DEVINS/DEVIN2_PROMPT.md`. Copy everything below the `---` line.
4. Replace `<SHARED_REPO_URL>` with the URL Devin 1 just gave you.
5. Replace `<TOPIC_FILE_URL>` with the **same** topic URL you gave Devin 1.
6. Paste into Devin 2's first message. Send.

### Step 4 — Wait for the debate

Devin 1 and Devin 2 will:

1. Each independently research the open internet (~30 min each).
2. Each write a round-1 spec (no peeking at each other) (~45 min each).
3. Cross-critique each other (~30 min).
4. Revise (~45 min).
5. Repeat critique / revise for up to 6 rounds total.
6. Synthesize into `final_spec.md` and ping you in the final PR.

**Expected total wall time:** 4-8 hours depending on topic complexity. They run in parallel, so don't sit and watch — get notifications and check back.

You **do not** intervene unless one of them is clearly stuck or off-topic. They self-coordinate via PR comments.

### Step 5 — Pick the better synthesis

Both Devin 1 and Devin 2 will open a `[FINAL]` PR with their synthesis version. They will (intentionally) differ. Read both and:

- Pick whichever you prefer **as-is**, OR
- Merge both into a hand-edited `final_spec.md` (merge the best parts), OR
- If both are bad, send a critical comment on both PRs and make them do another round.

**Tip:** if the topic was simple, the two specs will be ~80% the same. If the topic was hard, they'll differ a lot — that's where the value is.

### Step 6 — Launch Devin 3 (implementer)

1. Open https://app.devin.ai/new from a **third Devin account** (or reuse Devin 1 / Devin 2 — it doesn't matter, the model just needs to be capable).
2. In the model picker, pick a strong code model (Claude Opus 4.7 or Claude Sonnet 4.5 are both good).
3. Open `docs/PARALLEL_DEVINS/DEVIN3_PROMPT.md`. Copy everything below the `---` line.
4. Replace `<FINAL_SPEC_URL>` with the URL of the `final_spec.md` you accepted in step 5.
5. Paste into Devin 3's first message. Send.

Devin 3 will:

1. Read the spec.
2. Propose a PR breakdown to you. Approve.
3. Build it in small PRs.
4. After each PR, spawn a code-review sub-agent. If the sub-agent grades the PR < 9/10, fix and re-review (max 5 iterations per PR).
5. Open PRs for your review only when SCORE >= 9/10.

### Step 7 — Hand off to Main Devin (this session)

When Devin 3 is fully done and you've merged its PRs, the working tool exists in its own repo (e.g. `3mgeorgii/lilush-seo-v2`).

Come back to **this** Devin session (or open a fresh main Devin), and say:

> Готов инструмент в `3mgeorgii/<tool-name>`. Интегрируй его в Lilush.

The main Devin will read the new tool's README, write a small adapter in the Lilush repo, replace the v1 worker with the v2 tool, and open an integration PR.

## Why this works

- **No single LLM has all the answers.** Two heterogeneous models debating produces a better spec than either alone.
- **Specs and implementation are separated.** The agents writing the spec can't take shortcuts in implementation. The implementer has a clear contract.
- **Code review by a fresh sub-agent catches blind spots.** Implementing-Devin's own code review is biased; a fresh sub-agent with no shared context is more objective.
- **You stay in control.** You choose which spec to merge, you approve the implementation breakdown, you sign off final integration.

## Practical tips

- **Don't run more than 2 topics in parallel** until you've done one full pass. The workflow takes time to dial in.
- **If a topic file is too narrow**, the debate will be short and shallow. Make topics meaty (multiple open questions, real production constraints).
- **If a topic is too broad** (e.g. "redesign all of Lilush"), the agents will produce hand-wavy specs. Keep topics focused on one worker / one feature.
- **Don't accept a spec that doesn't resolve every open question** in the topic file. Send it back for another round.
- **Don't accept Devin 3's PR until SCORE >= 9/10.** That's the whole point of the loop — don't let them shortcut it.

## Limitations

- **Token cost.** Each Devin session costs Devin credits. A full SEO-v2 engagement (Devin 1 + Devin 2 debate + Devin 3 implement) might use 30-50% of a typical Devin monthly budget. Pace yourself.
- **No real-time chat between Devins.** They communicate via git only. This is intentional (auditable, async-friendly) but means rounds are slow.
- **Models named "Opus 4.7" and "GPT 5.5" may not exist.** If they don't yet, use the latest available in each family. The prompts are model-agnostic — only the launch step matters.

## Files in this folder

- `DEVIN1_PROMPT.md` — paste into Devin 1's first message
- `DEVIN2_PROMPT.md` — paste into Devin 2's first message
- `DEVIN3_PROMPT.md` — paste into Devin 3's first message after the debate is done
- `README.md` — this file
