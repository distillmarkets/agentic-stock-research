# Agent roles

Two roles produced every finding in this repository: a study agent and an
adversarial reviewer. The role text is here, tool-agnostic, and inherits every
rule in [../AGENTS.md](../AGENTS.md) rather than restating it.

| role | file | owes |
|---|---|---|
| study | [study.md](study.md) | one study folder a reviewer can try to break |
| review | [review.md](review.md) | one verdict per headline claim, nothing in the study edited |

## Claude Code

The roles are registered as subagents in `.claude/agents/`, and `CLAUDE.md`
imports `AGENTS.md`, so a Claude Code session in the checkout already knows
both. Ask in plain words:

```
Use the study agent. Question: how often does a firm with Altman Z below 1.8
stop filing within two years, whole record against the priced subset?
Budget: 50 uncached calls.
```

```
Use the review agent on research/pre-exit-signature.
```

## Codex

Codex reads `AGENTS.md` on its own. Hand it the role with the question:

```
codex "Take the role in agents/study.md. Question: ... Budget: 50 uncached calls."
codex "Take the role in agents/review.md on research/pre-exit-signature."
```

## Gemini CLI, Copilot, Cursor and the rest

Tools that read `AGENTS.md` get the brief automatically. `GEMINI.md` points at
it for tools that read that file instead. For any of them, the invocation is
the Codex one: name the role file and the question.

## What the roles do not do

Neither role rates, values, forecasts or recommends a security, and the
reviewer fails any sentence that does. There is no per-ticker analyst role here
by design.
