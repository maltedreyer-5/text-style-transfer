# Text Style Transfer

[![CI](https://github.com/maltedreyer-5/text-style-transfer/actions/workflows/ci.yml/badge.svg)](https://github.com/maltedreyer-5/text-style-transfer/actions/workflows/ci.yml)

Text Style Transfer derives a writing style from own text samples and makes it reusable. The
application analyses the samples, counts the features that can be counted, presents the result as
adjustable settings, applies them to test texts for comparison, and exports the style as an Agent
Skill. The same settings can be used within the
application to rewrite texts; 31 packaged profiles provide further styles.

The application processes texts in English, German, French, Spanish, Italian and Polish and offers
its interface in English and German. The language model is reached through an OpenAI-compatible
chat-completions endpoint configured by the operator.

## Functions

The tab *My style → skill* leads in four steps from an own text sample to a skill: analysis of the
sample, review and adjustment of the settings, trial on a test text, export.

The analysis counts sentence and paragraph length, punctuation, questions, quoted speech, word
length, lexical variety, personal pronouns, forms of address, hedging words, nominalisations and
list lines. These counts preset measured targets, such as the average sentence length, and are passed
to the model as evidence for the values of 34 style sliders. The model adds a style description and
rules. After each trial, a table compares source, target and result, and warnings point to missed
targets, sliders whose feature did not change in the intended direction, missing numbers and lost
quotations.

A style is held as a profile. Profiles are kept by the user as a one-line profile code, as a JSON file
or inside an exported skill; the server stores no profiles. Profiles can also be created from a
free-text description or refined from pairs of an original and an edited text.

For rewriting a text within the application, two paths are available. On the first path, the text is
neutralised and then given the target style; the neutral intermediate text can be edited and is
reused while text and settings remain unchanged. On the second path, the target style is applied to
the text directly.

## Quick start

The application requires Python 3.11 or later and an OpenAI-compatible chat-completions endpoint.

```bash
python -m venv .venv && . .venv/bin/activate
pip install -c constraints.txt .
cp .env.example .env          # set TST_LLM_BASE_URL, TST_LLM_API_KEY and TST_LLM_MODEL
text-style-transfer           # serves http://127.0.0.1:7860
```

With Docker:

```bash
cp .env.example .env          # adjust as above
docker compose up --build     # serves http://127.0.0.1:7860
```

Inside the container, `localhost` refers to the container itself. `TST_LLM_BASE_URL` must therefore
name an address that the container can reach.

## Security notice

The application has no user management of its own and listens on `127.0.0.1` by default. Access for
other people requires a reverse proxy that authenticates users; the details are described in
[SECURITY.md](SECURITY.md). Every text entered in the application is sent to the configured
language-model endpoint. The choice of endpoint determines how these texts are handled there.

## Documentation

The documentation starts at [docs/index.md](docs/index.md). The creation of a skill from an own text
and other common tasks are described step by step in [docs/workflows.md](docs/workflows.md).

## Contributing

Set-up, the definition of a verified change and the rules the code relies on are described in
[CONTRIBUTING.md](CONTRIBUTING.md). Changes are listed in [CHANGELOG.md](CHANGELOG.md). The project
follows a [code of conduct](CODE_OF_CONDUCT.md). Citation data is provided in
[CITATION.cff](CITATION.cff).

## Third-party components

| Component | License | Use |
|---|---|---|
| [Gradio](https://github.com/gradio-app/gradio) | Apache-2.0 | web interface |
| [openai-python](https://github.com/openai/openai-python) | Apache-2.0 | client for the chat-completions API |
| [python-docx](https://github.com/python-openxml/python-docx) | MIT | reading and writing Word files |
| [python-dotenv](https://github.com/theskumar/python-dotenv) | BSD-3-Clause | reading `.env` |

The dependencies of these components are pinned in `constraints.txt`. The metrics of the four classic
profiles were measured on public-domain texts from Project Gutenberg. These texts are not part of the
repository; their sources are listed in
[src/text_style_transfer/data/PROVENANCE.md](src/text_style_transfer/data/PROVENANCE.md).

## License

The software is licensed under the MIT License; see [LICENSE](LICENSE).
