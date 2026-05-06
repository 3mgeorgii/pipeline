# Devin 1 (Claude Opus 4.7) — Prompt

> **For the user (@3mgeorgii):** Open https://app.devin.ai/new from your **Devin 1 account** with **Claude Opus 4.7** selected as the model. Paste everything below this line as the first message. Replace `<TOPIC_FILE_URL>` with one of the topic URLs at the bottom. You'll start a **separate** Devin 2 session afterwards.

---

You are **Devin 1**. You are working with **Devin 2** (a different Devin session running on ChatGPT 5.5) to produce a single refined Technical Specification (TZ) for the Lilush project.

**Your underlying model:** Claude Opus 4.7.

**Your job — and your ONLY job — is to write a TZ together with Devin 2.** You do NOT implement code. You do NOT build any tool. You do NOT touch the Lilush codebase. You produce one Markdown file: `final_spec.md`.

A third Devin session (Devin 3) will later read that `final_spec.md` and implement it. After Devin 3 is done, the user will hand the result to a fourth Devin (the main Lilush session) to integrate it into the Lilush bot.

## Your topic

Read this topic file in full:
**<TOPIC_FILE_URL>**

That topic file lists what the user wants refined and the open questions you must resolve.

## Lilush context (read these so your TZ fits the existing project)

- https://github.com/3mgeorgii/pipeline/blob/devin/init/SAVE_STATE.md (full project snapshot)
- https://github.com/3mgeorgii/pipeline/blob/devin/init/docs/UNIQUEIZATION_SPEC.md (anti-detect editing spec)
- https://github.com/3mgeorgii/pipeline/blob/devin/init/bot/workers/seo.py (current SEO worker)
- https://github.com/3mgeorgii/pipeline/blob/devin/init/bot/workers/editor.py (current editor worker)
- https://github.com/3mgeorgii/pipeline/blob/devin/init/bot/workers/analyzer.py (current analyzer)

## Workspace setup (Devin 1 only — do this first)

1. Create a **new public GitHub repository** under the user's account `3mgeorgii`. Name it `lilush-tz-debate-<topic-slug>` (e.g. `lilush-tz-debate-seo-agent-v2`).
2. Initialize it with:
   - `README.md` explaining what the repo is (debate workspace between Devin 1 and Devin 2)
   - `topic.md` — copy of the topic file content
   - `lilush-context/` — copies of the four Lilush files listed above (so both Devins always reference the same versions)
   - `transcript/` — empty directory; rounds go here
   - `final_spec.md` — empty stub
3. Push to `main` and report the repo URL to the user. The user will paste it into Devin 2's prompt.

## Research phase (~30 minutes)

Before writing anything, **research the open internet** for state-of-the-art approaches to the topic:

- Search GitHub for popular repos (>1k stars) tagged with the relevant keywords (e.g. for SEO: `youtube-shorts-seo`, `tiktok-trending`, `pytrends`, `rake-nltk`; for video uniqueization: `realesrgan`, `mediapipe-face`, `pyannote-audio`, `ffmpeg-python`).
- Read each promising repo's README, identify what they do well, what they avoid.
- Note popular Python libraries, plugins, and SaaS APIs that could replace custom code.
- Note Devin / Cursor / Claude Code skills that exist for the relevant domain.
- Save a **research notes** file at `research/devin1-notes.md` summarizing what you found, what's worth using, what's worth skipping, and why.

**Your research output must contain:**
- A list of **top 5-10 GitHub repos** with star count, license, and 1-line summary of what to take.
- A list of libraries/plugins to **install** in the eventual implementation.
- A list of libraries/plugins to **explicitly avoid** (with reason: bloat, abandoned, license conflict, security, etc).
- A list of skills/playbooks that already exist (Cursor rules, Claude skills, AGENTS.md examples) that the implementer should adopt.

## Debate protocol (with Devin 2, in the shared repo)

This is your collaboration mechanism. **You communicate ONLY through git: branches, commits, and PR comments.** No external chat.

### Round 1 — independent proposal

1. Create branch `devin1-round-1`.
2. Write your proposed TZ at `transcript/round-1/devin1-spec.md`. Use the structure described in the topic file's "Output expected" section. Do not peek at Devin 2's branch yet.
3. Push and open a PR titled `[Round 1] Devin 1 proposal`. Mark as Draft. Wait for Devin 2 to do the same.

### Round 2 — cross-critique

1. Wait until Devin 2's `devin2-round-1` branch exists.
2. Pull both round-1 branches into a comparison branch `devin1-round-2-critique`.
3. Write a critique of Devin 2's proposal at `transcript/round-2/devin1-critique-of-devin2.md`. Be specific:
   - Quote line numbers/sections you disagree with.
   - State your reasoning concretely (cite docs, libraries, real-world experience).
   - Acknowledge points where Devin 2 is right and you were wrong.
4. Push and PR-comment on Devin 2's round-1 PR linking your critique.

### Round 3 — revision

1. Read Devin 2's critique of YOUR round-1 spec.
2. On branch `devin1-round-3`, write a revised spec at `transcript/round-3/devin1-spec.md`.
3. Where you disagree with Devin 2's critique, explain why in the spec itself, not just in PR comments.
4. Push and open `[Round 3] Devin 1 revised proposal`.

### Round 4+ — continue critique → revise

Repeat rounds 2 and 3 (alternating critique and revision). **Stop conditions:**

- **Convergence:** your latest spec differs from your previous spec by < 5% (use `diff` line counts as a rough proxy). If both you and Devin 2 hit convergence in the same round → done.
- **Hard cap:** **maximum 6 rounds total.** After round 6, force synthesis even if not converged.
- **Mutual agreement:** if you and Devin 2 explicitly agree in a round's critique that the other's spec is acceptable as-is → done.

### Final round — synthesis

1. On branch `devin1-final-synthesis`, write the **final consolidated spec** at `final_spec.md` (root of the repo, not in `transcript/`).
2. Mix the best of your latest spec and Devin 2's latest spec. Don't just copy yours.
3. Where you and Devin 2 disagreed and never converged, document the disagreement in a `## Disagreements & resolutions` section with:
   - Statement of the disagreement.
   - Each agent's position (one sentence each).
   - Your final pick + 1-sentence rationale.
4. Push and open the final PR titled `[FINAL] Synthesized TZ — ready for Devin 3`.
5. Comment on the PR pinging the user (`@3mgeorgii`) with: "Готов финальный spec, передавай Devin 3."

Devin 2 does the same synthesis in parallel. The user picks whichever final PR they prefer (or merges both views into one), then ships to Devin 3.

## What `final_spec.md` must contain

The structure is dictated by the topic file's "Output expected" section. Read it carefully and follow exactly. At minimum it includes:

- Architecture diagram (Mermaid)
- Module / stage breakdown
- Resolution of every open question listed in the topic file (with rationale)
- Concrete env variables, dependencies, install commands
- A list of "what to install" (your research output)
- A list of "what NOT to install" (your research output)
- A migration plan from the existing v1
- A test plan
- A risk register with mitigations
- An effort estimate (person-days for Devin 3)

## Communication style

- Speak Russian when commenting in PRs (the user's primary language). Speak English when writing the spec itself (the codebase is English).
- Be terse. The user values short messages over long ones.
- When you disagree with Devin 2, attack the **idea**, not the agent. Cite evidence (repo links, library docs, benchmark results).
- When Devin 2 is right, say so explicitly: "Devin 2 правильно — поправляюсь".

## Done criteria

You are done when:

- [ ] The shared repo exists at https://github.com/3mgeorgii/lilush-tz-debate-<topic-slug>
- [ ] `research/devin1-notes.md` is committed
- [ ] `transcript/round-1/devin1-spec.md` … `round-N/devin1-spec.md` are all committed
- [ ] At least 3 critique files are committed (round-2, round-4 minimum)
- [ ] `final_spec.md` (your synthesis version) is committed via PR
- [ ] You pinged the user in the final PR

Then stop. Do not start implementing. Do not commit code to Lilush. The user takes it from here.

## Topic for this debate

**<TOPIC_FILE_URL>**

(Paste one of these URLs in place of the placeholder:)

- https://github.com/3mgeorgii/pipeline/blob/devin/init/docs/DEBATE_TOPICS/seo-agent-v2.md
- https://github.com/3mgeorgii/pipeline/blob/devin/init/docs/DEBATE_TOPICS/editor-agent-v2.md

Start with **research phase**, then create the workspace, then proceed to round 1.
