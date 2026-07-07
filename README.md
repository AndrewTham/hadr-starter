# HADR Monitor

A monitoring agent for humanitarian assistance and disaster response (HADR).

This is a **course starter template**, not a finished project. It hands you the
inputs (live disaster feeds), the target, and a set of empty places to put your
work — and deliberately leaves *how* to build the agent unspecified. That gap is
the course.

## The end state

By Wednesday afternoon this repository contains an agent that:

- watches live disaster feeds — GDACS, USGS and ReliefWeb (see `feeds/`)
- filters out the noise and assesses what remains: what happened, where, how bad, who is affected
- publishes a morning situation report to `dashboard.html` at 08:30 Singapore time
- runs on a schedule, unattended, and stays quiet when nothing has changed

How it does any of that is not specified anywhere in this repository. That is the course.

## The three days

1. **Plan** — interrogate the feeds, write the PRD, cut it into vertical slices
2. **Autonomy** — build the first slice, write a skill, wire up the 08:30 routine, launch the overnight loop
3. **Trust** — review code you didn't write, harden the pipeline, demo

## Repository map

Everything here is either **reference you read** or a **placeholder you fill in**.
Nothing contains the actual agent yet — you build that.

| Path | What it is | Who fills it in |
| --- | --- | --- |
| `README.md` | This file — the brief and the map. | given |
| `CLAUDE.md` | Project conventions the agent must follow (language, test command, style, deviations policy). **Fill in before your first prompt.** | you (Day 1) |
| `feeds/` | Reference notes on the three data sources — endpoints, example payloads, and the hard questions each feed raises (dedup, revisions, rate limits). Read these first. | given |
| `feeds/gdacs.md` | GDACS multi-hazard feed (EU/UN), colour-coded alert levels. | given |
| `feeds/usgs.md` | USGS real-time earthquake GeoJSON feed. | given |
| `feeds/reliefweb.md` | ReliefWeb (UN OCHA) curated disasters + RSS fallback. | given |
| `scripts/` | Deterministic checks and tooling. Anything that must give the same answer twice lives here, **not** in a prompt (e.g. the change-detection script the morning routine branches on). | you |
| `skills/` | Skills you author on Day 2, one folder per skill (a `SKILL.md`, its assets, and which model each step should use). | you (Day 2) |
| `docs/solutions/` | A knowledge base of hard-won fixes — one learning per file, so no future session pays for the same debugging twice. Grep here before debugging. | you (ongoing) |
| `implementation-notes.md` | Running log kept by the agent, reviewed by you: decisions, open questions, and any deviation from the PRD or `CLAUDE.md` (an undocumented deviation is a bug). | you + agent |
| `.github/workflows/sitrep.yml.disabled` | The morning-routine scaffold. Deterministic check decides whether anything changed; a headless model call runs *only* if it did. Rename to `.yml` once both TODOs exist. | you (Day 2) |
| `.github/workflows/claude*.yml` | @claude PR review and code-review automation (wired up by `/install-github-app`). | given |
| `.github/ISSUE_TEMPLATE/` | Issue templates for vertical slices and skill feedback. | given |
| `.gitignore` | Ignores generated reports and secrets; `dashboard.html` is the committed exception because it *is* the product. | given |

## Artefacts expected by the end

These are the deliverables you produce — none exist in the starter yet:

`prd.html` · `system-view.html` · `implementation-notes.md` · `dashboard.html` · `goal.md` · at least one skill

## Day 1 setup

1. Sign in to Claude Code with your Team seat
2. Create your own repository from this template, then clone it
3. Run `/install-github-app` so @claude reviews your pull requests from Day 2
4. Install OpenCode and sign in with your Go key

Fill in `CLAUDE.md` before your first prompt.

## How the pieces fit together

The intended shape of the running system (which you design and build):

```
disaster feeds ──► deterministic fetch + change detection (scripts/)
   (feeds/)              │
                         │  something changed?
                         ▼  yes ──► model assesses & writes report (skills/)
                                          │
                                          ▼
                                    dashboard.html  ◄── published 08:30 SGT,
                                                        unattended, on a schedule
                                                        (.github/workflows/sitrep.yml)
```

The rule that runs through the whole design: **the model never decides whether
to wake up.** A deterministic script does. The model only runs once there is
something worth reporting.
