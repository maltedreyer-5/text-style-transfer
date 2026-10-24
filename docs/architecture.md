# Architecture

## Overview

```
browser ──HTTP──▶ ui/app.py (Gradio) ──▶ core/pipeline.py ──▶ core/llm.py ──HTTP──▶ language model
                     │                         │
                     │                         ├─ core/prompts.py     instructions to the model
                     │                         ├─ core/cleanup.py     removal of introductions, reasoning, fences
                     │                         ├─ core/checks.py      checks of the result
                     │                         ├─ core/metrics.py     sentence and paragraph values
                     │                         └─ core/indicators.py  countable features per language
                     ├─ core/skill.py   profile → SKILL.md, using the building blocks of core/prompts.py
                     ├─ ui/session.py   session state and temporary files
                     ├─ ui/security.py  response headers, proxy authentication
                     └─ i18n.py         interface texts in English and German
core/catalog.py ── reads data/ at start: sliders, groups, conflicts, profiles, language packs
```

The package `core/` does not import Gradio and can be used and tested without the interface.

## Modules

| Module | Responsibility |
|---|---|
| `config.py` | reading and validation of the `TST_` variables |
| `core/models.py` | data types: sliders, profiles, neutralisation settings, issues |
| `core/catalog.py` | loading and checking of the packaged data; an inconsistency stops the start |
| `core/profiles.py` | profile JSON version 1: validation and serialisation |
| `core/profile_code.py` | profile code version 1 (`tsp1.`) |
| `core/prompts.py` | instructions for neutralisation, styling, analysis and refinement |
| `core/pipeline.py` | the two paths, analysis, creation from a description, refinement |
| `core/llm.py` | the client for the endpoint, with the only retry layer |
| `core/cleanup.py` | removal of introductions, reasoning blocks and code fences from model answers |
| `core/checks.py` | checks of numbers, quotations, length, language, targets and slider directions |
| `core/metrics.py` | sentence length, paragraph length, punctuation and similar values |
| `core/indicators.py` | countable features per language: pronouns, forms of address, hedging words, nominalisations, list lines, word length, lexical variety |
| `core/documents.py` | reading of uploads, writing of exports |
| `core/tokens.py` | token estimate without a tokenizer |
| `core/skill.py` | export of a profile as an Agent Skill, validated against the format rules |
| `ui/app.py` | layout (side bar with the settings, guided tab, further tabs), events, launch with the privacy defaults |
| `ui/session.py` | session data and the temporary directory of a session |

## Data

| File | Content |
|---|---|
| `data/sliders.json` | 34 sliders: id, type, group, labels and descriptions in English and German, English instructions per pole |
| `data/groups.json`, `data/conflicts.json` | seven groups; twelve known conflicts with explanations |
| `data/lang/<code>.json` | one language pack per text language: example words for 16 features, number format, quotation marks, patterns for introductory and closing remarks, function words, abbreviations, word lists for the countable features |
| `data/profiles/<id>.json` | 31 packaged profiles in the public profile format |
| `data/ui/<code>.json` | interface texts |

## Course of a run

1. The interface assembles the current profile from the chosen profile, the sliders, the measured
   targets, the neutralisation settings and the description in the interface language.
2. `Pipeline.run` checks the input size. On the neutral path it neutralises the text unless a neutral
   text for the same input and settings is available.
3. The styling instructions list the active features in descending strength, with dosage and with the
   example words of the text language, followed by description, rules, targets, target length and the
   rules against additions.
4. Each answer is cleaned. An answer that describes the task instead of carrying it out is requested
   once more with an additional instruction.
5. Source and result are measured. The result is checked against the targets and against the
   direction of strong sliders and is added to the history of the session.

## Invariants

The rules that the code relies on, and the tests that cover them, are listed in
[CONTRIBUTING.md](../CONTRIBUTING.md#architecture-invariants).

## Limits

- One process holds all sessions in memory. Several processes behind a load balancer would require
  sticky sessions.
- The interface is rendered by Gradio and requires JavaScript in the browser.
