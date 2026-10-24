# Contributing

## Language

Code, comments, documentation, commit messages, issues and pull requests are written in English.
Interface texts are kept in `src/text_style_transfer/data/ui/en.json` and `de.json`; a new text is
added to both files. Language-specific content for the model is kept in
`src/text_style_transfer/data/lang/<code>.json`, written in the respective language; a new entry is
added to all six files.

The documentation describes the current state in the style of a reference text: declarative
sentences in the present tense, defined terms, and limits stated as separate sentences.

## Set up

```bash
python -m venv .venv && . .venv/bin/activate
pip install -c constraints.txt -e ".[dev]"
```

## Definition of "verified"

A change is verified when the following commands succeed. The CI workflow runs the same commands.

```bash
python -m ruff check src tests tools
python -m compileall -q src tests tools
python -m pytest
python tools/check_docs.py
python tools/check_repo.py
```

## Architecture invariants

A violation of one of the following rules usually causes no error message; it changes the behaviour
for users without notice. The last column names the test or check that covers each rule.

| # | Invariant | Reason | Guarded by |
|---|---|---|---|
| 1 | No displayed text is a key, a comparison value or prompt content. Sliders, stages and profiles have stable English ids; labels (UI) and instructions (prompt) are separate fields. | A translated label must never change behaviour. | `test_choice_values_are_ids_not_labels` |
| 2 | No user data at module level; everything per user lives in `SessionData`. | Gradio serves all sessions from one process; a module-level variable is shared by every user. | `test_run_isolation_and_no_outbound` |
| 3 | Exactly one retry layer, in `core/llm.py`; the SDK's retries stay off. | Stacked retries multiply the attempts and the load on a shared server. | `test_exactly_one_retry_layer` |
| 4 | Packaged data is read-only and validated at start; the application writes neither into its package nor into its working directory. | A partial catalogue would silently drop style features. | `test_profile_directory`, teardown of the `app` fixture |
| 5 | Validation never uses `value or default`. | An empty value of the wrong type (`[]` where an object is required) must be rejected, not replaced. | `test_structural_errors_are_rejected` |
| 6 | Gradio `I18n` objects are never formatted or joined; messages with parameters go through `Translator.t()`. | `.format()` silently returns the untranslated placeholder; only the first placeholder of a string is translated. | `test_i18n_objects_are_never_formatted_or_joined` |
| 7 | No privileged events; every event works only on the caller's session. | Hidden events can still be called. | review rule (no automatic test) |
| 8 | No user content in logs or error messages; messages come from the catalogue. | Logs are read by other people than the users. | teardown of the `app` fixture |
| 9 | Uploads are deleted right after reading. | Gradio serves cached files to anyone with the URL. | `test_upload_is_deleted_after_reading` |
| 10 | No outbound connections except to the configured endpoint. | Texts and usage data must not leave towards third parties. | `test_run_isolation_and_no_outbound`, `test_guard_blocks_outbound` |

## Data formats

The packaged data is stored in `src/text_style_transfer/data/` and is checked at every start. An
error message names the file and the problem.

### `sliders.json`

The file contains the list of sliders.

| Field | Content |
|---|---|
| `id` | lowercase, digits, `_`; never changed once released (profiles refer to it) |
| `type` | `polar` (−10 to +10), `intensity` (1 to 10) or `stages` |
| `group` | id from `groups.json` |
| `labels`, `descriptions` | `{"en": …, "de": …}` for the interface |
| `opposite_labels` | polar only, `{"en": …, "de": …}` |
| `positive`, `negative` | `heading` and `instruction` in English (prompt only), `markers` in English, optional `example_key` into the language packs; `negative` for polar only |
| `stages` | stages only: list of `{"id", "instruction", "labels": {"en", "de"}}` |

### `lang/<code>.json`

Each file describes one text language.

| Field | Content |
|---|---|
| `code`, `endonym`, `english_name` | for example `fr`, `Français`, `French` |
| `examples` | the same 16 keys in every pack; example words in that language |
| `decimal_separator`, `group_separators` | number format used by the checks |
| `quotes` | pairs of opening and closing quotation marks |
| `preamble_patterns`, `trailer_patterns` | regular expressions (case-insensitive) for lines the cleanup removes |
| `function_words` | at least 20 frequent words, used to detect the language of a text |
| `abbreviations` | abbreviations that do not end a sentence |
| `indicators` | `personal`, `formal_address`, `familiar_address` (or `familiar_regex`), `formal_case_sensitive`, `hedges`: lists of words or phrases (an entry ending in `'` matches an elision such as French `j'`); `nominal_suffix`: regular expression applied to words of six letters or more |

### `profiles/<id>.json`

Each file contains one profile in the public profile format (see `docs/design/profile-format.md`),
with `id` equal to the file name and with `labels` and `descriptions` in English and German.

### `ui/<code>.json`

Each file maps keys to interface texts. Placeholders in `{braces}` are identical in every language.

## Typical changes

| Change | Steps |
|---|---|
| New slider | Add the slider to `data/sliders.json`. If an instruction needs language-specific examples, add the example key to all six language packs. |
| New packaged profile | Add `data/profiles/<id>.json`. A classic profile also needs an entry in `data/PROVENANCE.md` with the public-domain sources of its measurements. |
| New interface text | Add the key to both interface catalogues. |
| New interface language | Add `data/ui/<code>.json` with all keys, add the language to every `labels`, `descriptions` and `hints` object in the data files, and add the code to `UI_LANGUAGES`. |
| New interface event | Register it after the existing events in `ui/app.py`. Gradio numbers events with the same function name in the order of registration (`run`, `run_1`, …), and the interface tests address events by these names. |
| Updated dependencies | Install with each supported Python version without `constraints.txt`, run the tests, save `pip freeze` per version and merge the outputs with `python tools/merge_constraints.py 3.11=… 3.12=… 3.13=… > constraints.txt`. Packages that differ between versions receive environment markers. |
| Changed limit or default | Update the documentation in the same change. `tests/test_docs.py` compares the figures and defaults stated in the documentation with the code. |
| Skill export | The format rules are implemented in `core/skill.py` and checked by `tests/test_skill.py`. A change of the published format requires changes in both files. |
| New text language | Add `data/lang/<code>.json` with every example key and indicator list, and add the code to `TEXT_LANGUAGES`. |

## Releasing

1. Set the version in `src/text_style_transfer/__init__.py`, `CITATION.cff` and the image tag in
   `compose.yaml`; add a section to `CHANGELOG.md`. `tools/check_repo.py` fails if they differ.
2. Run every command of "verified".
3. Tag the commit `vX.Y.Z` and create a GitHub release from the changelog section.

## Pull requests

A pull request describes the change from the users' point of view. The documentation in `docs/` is
updated in the same pull request and describes the resulting state.
