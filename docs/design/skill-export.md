# Export as a skill

## Decision

The current settings can be exported as an Agent Skill: a ZIP archive with one folder that contains
`SKILL.md` and `profile.json`.

## Content

| Part | Source |
|---|---|
| `name` | `writing-style-` followed by the profile name in lowercase ASCII (umlauts as `ae`, `oe`, `ue`), at most 64 characters |
| `description` | what the skill does (style name, text language if the profile has one, the strongest features) and when it is to be used |
| Procedure | keep the language; neutralise first if the source has a pronounced style (dimensions and depth from the profile); apply the features; check; answer without introduction |
| Style features | the feature lines of the application's own instructions, in descending strength, with dosage |
| Language-specific hints | the example words of the active features, for the language of the profile or, for a language-neutral profile, for all six languages |
| Description, rules, measured targets | from the profile; the targets as set in the interface |
| Length, invariable rules, final check | the rules the application uses against additions and changed facts |
| `profile.json` | the profile in the public format, for loading it into the application again |

The instructions are written in English, as are the application's own instructions. The description of
the profile remains in the language of the person who created it. The reference texts are not part of
a profile and therefore not part of a skill.

## Format rules

The export follows the published format
([Agent Skills overview](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)):

- `name` has at most 64 characters, consists of lowercase letters, digits and single hyphens, and does
  not contain the words `anthropic` or `claude`.
- `description` is not empty, has at most 1,024 characters and contains no angle brackets. It states
  what the skill does and when it is to be used.
- The instructions are to stay below about 5,000 tokens; a longer export is reported.
- Each skill consists of one `SKILL.md` in a folder of the same name.

`tests/test_skill.py` checks these rules, including names derived from hostile input.

## Installing an exported skill

- claude.ai: upload the ZIP archive under Settings > Features. Custom skills require a plan with code
  execution enabled.
- Claude Code: unpack the folder into `~/.claude/skills/` for personal use or into `.claude/skills/`
  of a project.
- Claude API: upload the skill through the Skills API.

Skills are not synchronised between these environments; each requires its own upload. The official
documentation describes the current procedures.

## Limits

- A skill contains instructions. The neutralisation becomes a working step that the model is asked to
  carry out, and the checks of the application for numbers, quotations, length, language and targets
  are not performed where the skill is used.
- The quality of the result depends on the model that applies the skill.
- The format is defined by Anthropic. Other tools may read `SKILL.md` files; this is not tested.
- The description, rules and own sliders of a profile are copied into the skill unchanged. A skill
  should be read before it is passed on. Skills from other people should be used only if their source
  is trusted.
