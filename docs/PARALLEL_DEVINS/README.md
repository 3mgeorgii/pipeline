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
5. Continue critique → revise rounds. Each round 3+ MUST introduce a new perspective (anti-collusion rule).
6. If they appear to agree before round 3 → they automatically run 2 adversarial rounds (skeptical-engineer mode) before being allowed to converge.
7. **Stop only when both post `APPROVED` comments** on the same spec PR.
8. Hard safety cap of 15 rounds (failure mode — should not be reached).

**Expected total wall time:** 4-8 hours for a focused topic; can run overnight for harder topics. They run in parallel, so don't sit and watch — get notifications and check back.

You **do not** intervene unless one of them is clearly stuck or off-topic. They self-coordinate via PR comments.

### Step 5 — Read the approved final spec

When both Devins post `APPROVED` and open the `[FINAL]` PR, there is **one** `final_spec.md` at the root of the shared repo. Both agents signed off.

Read it. If you're satisfied, merge the PR and proceed to step 6.

If you read it and disagree with something, you have two options:

- **Light edit**: hand-modify the spec yourself before passing to Devin 3.
- **Reopen debate**: comment on the `[FINAL]` PR with your concrete objection and tell both agents to do another adversarial round addressing it.

If they hit the 15-round emergency stop without agreement, you'll see an `[EMERGENCY STOP]` PR listing 3-5 unresolved disagreements — you have to make the final calls and create the unified spec yourself, then proceed.

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
- **Mutual agreement is the only stop condition.** No diff-based heuristics, no fixed round count. The debate ends when *both* agents post `APPROVED` on the same spec — forcing real consensus instead of LLM politeness.
- **Anti-collusion rule.** From round 3 onwards, each agent must introduce a new perspective every round. Cuts off the failure mode where both LLMs converge on a popular-but-wrong answer.
- **Dig-deeper rule.** If they agree before round 3, the protocol forces 2 adversarial rounds (skeptical-engineer mode) before convergence is allowed.
- **Specs and implementation are separated.** The agents writing the spec can't take shortcuts in implementation. The implementer has a clear contract.
- **Code review by a fresh sub-agent catches blind spots.** Implementing-Devin's own code review is biased; a fresh sub-agent with no shared context is more objective.
- **You stay in control.** You read the agreed spec, you approve the implementation breakdown, you sign off final integration.

## Practical tips

- **Don't run more than 2 topics in parallel** until you've done one full pass. The workflow takes time to dial in.
- **If a topic file is too narrow**, the debate will be short and shallow. Make topics meaty (multiple open questions, real production constraints).
- **If a topic is too broad** (e.g. "redesign all of Lilush"), the agents will produce hand-wavy specs. Keep topics focused on one worker / one feature.
- **Don't accept a spec that doesn't resolve every open question** in the topic file. Comment on the `[FINAL]` PR and tell both agents to do another adversarial round on the missing question.
- **Don't accept Devin 3's PR until SCORE >= 9/10.** That's the whole point of the loop — don't let them shortcut it.
- **Watch for the `NO NEW PERSPECTIVE` escape hatch.** If you see this phrase in a round 3+ commit, it's allowed but rare. If it appears 2+ times in a row, the agents are running out of ideas and you should consider the spec close to done.

## Limitations

- **Token cost.** Each Devin session costs Devin credits. A full SEO-v2 engagement (Devin 1 + Devin 2 debate + Devin 3 implement) might use 30-50% of a typical Devin monthly budget. Pace yourself.
- **No real-time chat between Devins.** They communicate via git only. This is intentional (auditable, async-friendly) but means rounds are slow.
- **Models named "Opus 4.7" and "GPT 5.5" may not exist.** If they don't yet, use the latest available in each family. The prompts are model-agnostic — only the launch step matters.

## Files in this folder

- `DEVIN1_PROMPT.md` — paste into Devin 1's first message
- `DEVIN2_PROMPT.md` — paste into Devin 2's first message
- `DEVIN3_PROMPT.md` — paste into Devin 3's first message after the debate is done
- `README.md` — this file
