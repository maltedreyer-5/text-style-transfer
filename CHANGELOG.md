# Changelog

All notable changes are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/). The public interfaces covered by the version number are
the profile JSON format, the profile code and the `TST_` configuration variables.

## [1.0.0] - 2026-10-24

First public release.

- Guided tab in four steps from an own text sample to an Agent Skill: analysis, review and
  adjustment of the settings, trial on a test text, export.
- Rewriting of texts in English, German, French, Spanish, Italian and Polish through an
  OpenAI-compatible chat-completions endpoint.
- Two paths: neutralisation followed by styling, with an editable and reusable intermediate text, and
  direct styling. Neutralisation alone when no target style is set.
- 34 style sliders in seven groups; report of known conflicts between sliders.
- Measured targets for sentence length, paragraph length, punctuation, questions, exclamations and
  quoted speech; preset by the analysis and editable.
- Countable indicators per language (personal pronouns, forms of address, hedging words,
  nominalisations, list lines, word length, lexical variety), used as evidence for the analysis and
  for checking the result.
- 31 packaged profiles, among them four classic profiles with targets measured on public-domain texts.
- Profiles derived from reference texts or from a description; the analysis uses the same scale as
  the application of a profile and reports slider values that contradict unambiguous counts.
- Refinement from pairs of an original and an edited text; editable description and rules; own
  sliders within a profile.
- Profile code `tsp1.` and profile JSON format version 1.
- Export of the current settings as an Agent Skill (ZIP archive with `SKILL.md` and `profile.json`),
  validated against the published format rules.
- Checks of the result: numbers, quotations, length, input and output language, profile language,
  measured targets, direction of strong sliders, contradictions between targets and sliders; a table
  of source, target and result after each run.
- Side bar with the settings that apply in every tab; areas with settings open automatically when a
  profile is chosen.
- Interface in English and German.
- Privacy defaults: data held only in the session; browser run history, telemetry and the monitoring
  endpoint disabled; uploads deleted after reading; no user content in logs; local address by
  default; security headers.
- Optional authentication through a header set by a reverse proxy; optional read-only profile
  directory; optional privacy notice.
- Image definition for Docker and a compose file.

[1.0.0]: https://github.com/maltedreyer-5/text-style-transfer/releases/tag/v1.0.0
