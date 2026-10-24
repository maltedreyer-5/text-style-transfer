# Functional description

The application derives a writing style from own text samples, makes it adjustable and exports it as
an Agent Skill; the same settings rewrite texts. The interface consists of a side bar with the
settings and seven tabs. This chapter describes the
side bar and the tabs. Step-by-step instructions for common tasks are given in
[Workflows](workflows.md).

## Side bar *Settings*

The side bar contains the settings that apply in every tab: the choice of the profile, the
neutralisation settings, the style sliders and the measured targets. It is closed when the page is
loaded and opens after an analysis in the guided tab. When a profile is chosen, the areas that
contain its sliders and targets are opened.

## My style → skill

The guided tab leads in four steps from an own text to a skill:

| Step | Content |
|---|---|
| *1 Text sample* | own text (pasted or uploaded), text language, name of the style, *Analyse style* |
| *2 Settings* | list of the sliders and targets set by the analysis, notes on contradicting counts, editing of description and rules |
| *3 Try out* | test text, *Style directly* or *Neutralise, then style*, result with warnings and measurement table, previous attempt for comparison |
| *4 Export* | *Export as skill (ZIP)*, *Create profile code* |

A successful analysis moves to step 2 and opens the side bar. The buttons *Continue* and *Back*
switch between the steps. The tab uses the functions described below for *Copy a style*,
*Transform* and *Profile*, with the same settings and the same own profile.

## Transform

### Input

A text is entered in *Text* or uploaded as `.txt`, `.md` or `.docx`. An uploaded file is read once and
then deleted on the server; only the extracted text is kept in the memory of the session.

*Text language* states the language of the text. It is preset from the language reported by the
browser: a browser set to French receives an English interface and French as text language.
Choosing a profile does not change the text language. The result is written in the text language;
the application does not translate.

### Profiles and sliders

*Profile* in the side bar selects a packaged profile, the own profile of the session, or no profile.
Choosing a profile sets the sliders, the neutralisation settings and the measured targets of the
profile. All settings can be changed afterwards.

There are three kinds of slider:

| Kind | Range | Example |
|---|---|---|
| Two poles | −10 to +10 | *Formal ↔ Informal* |
| Intensity | 1 to 10 | *Ironic* |
| Stages | fixed values | *Language level (CEFR)* A1 to C2, *Audience age* |

A slider takes effect when it is marked *active*. Moving a slider marks it as active. In the
instructions to the model, stage sliders come first and the other sliders follow in descending
strength; a slider listed earlier takes precedence in a conflict. Twelve known conflicts between
sliders, for example *Objective* and *Dramatic*, are reported next to the result.

### Measured targets

*Measured targets* in the side bar contains seven values that the result is to approach:

| Target | Range |
|---|---|
| Words per sentence | 3 to 60 |
| Variation of sentence length (words) | 0 to 30 |
| Sentences per paragraph | 1 to 15 |
| Commas per sentence | 0 to 5 |
| Questions, exclamations, sentences with quoted speech | 0 to 100 % each |

The analysis of reference texts presets the targets; the classic profiles contain targets measured on
the authors' works. A target takes effect when it is marked *active*.

### Paths

*Neutralise, then style* first removes the style of the source along the selected dimensions (for
example tone, register, redundancy) and at the selected depth of intervention (gentle, normal,
thorough). The neutral text appears in its own field and can be edited. The target style is then
applied to it. While text and neutralisation settings remain unchanged, the neutral text, including
manual corrections, is reused.

*Style directly* applies the target style to the source as it is.

If no profile is chosen and no slider or target is active, there is no target style. In this case
*Style directly* does not run, and *Neutralise, then style* returns the neutral text as result. If no
neutralisation dimension is selected, *Neutralise, then style* styles the text directly and adds a
note.

### Result, checks and measurements

The result can be copied or exported as `.txt`, `.md` or `.docx`, optionally together with the
original. The checks below the result are warnings and do not block a result:

| Check | Condition for a warning |
|---|---|
| Numbers | a number of the source is missing in the result (compared in the number format of the text language) |
| Quotations | fewer quotations are marked in the result than in the source |
| Length | the result has less than half or more than 125 % of the target length (sources of 30 words or more) |
| Language | source or result appear to be written in another of the six languages (30 words or more) |
| Profile language | the profile was made for another text language |
| Targets | the result differs from a target by more than a tolerance: for words per sentence the larger of 3 words and 30 % of the target; for commas per sentence the larger of 0.5 and 50 %; for sentences per paragraph the larger of 1.5 and 50 %, checked for results with three paragraphs or more; for questions and exclamations 15 percentage points |
| Slider direction | for sliders set to 4 or more in either direction: the counted feature of *Personal*, *Hedging*, *Nominal*, *Structured* or *Simple* did not change in the direction of the slider compared with the source; for *Formal*, the forms of address in the result contradict the setting |
| Targets and sliders | a target contradicts a slider, for example *Simple* with a target of more than 20 words per sentence |

A table below the warnings lists, for source, target and result, the counted features: words per
sentence, sentences per paragraph, commas per sentence, questions, exclamations, letters per word,
lexical variety, personal pronouns, formal and familiar forms of address, hedging words,
nominalisations and list lines. Counting requires at least 40 words.

## Copy a style

*Analyse style* derives a profile from up to ten reference texts. The texts are pasted or uploaded and
separated by a line that contains only `---`. The application counts the countable features of the
texts and passes the counts to the model together with the texts and with the scale on which slider
values are applied. For the sliders *Personal*, *Formal*, *Hedging*, *Nominal* and *Structured*, the
model is instructed to base the value on the count. The model returns slider values, a description of
up to 120 words and up to five rules, written in the interface language.

The result becomes the own profile. Its measured targets are preset from the counts when the texts
contain about 80 words and five sentences or more. A slider value that contradicts an unambiguous
count is reported, for example *Hedging* set to 4 or more for texts without any hedging word.

*Create profile from description* turns a free-text description into a profile without counts.

## Refine

The tab collects up to five pairs of an original text and an edited version. *Derive rules* asks the
model for rules that describe the differences and adds them to the own profile, up to twelve rules in
total. Rules can be removed by number. If a packaged profile is selected at that moment, the current
settings first become the own profile, replacing an earlier own profile; a note reports this.

## Profile

| Function | Effect |
|---|---|
| *Show current settings as profile* | shows the profile as it is currently set |
| *Create profile code* | creates a one-line code starting with `tsp1.` that contains the whole profile |
| *Load code* | restores a profile from a code |
| *Download as JSON file*, *upload a profile JSON file* | stores or restores a profile as a file |
| *Edit description and rules* | changes the description and the rules of the own profile; slider and target settings are kept |
| *Own sliders* | adds up to five sliders with an own instruction to the own profile |
| *Export as skill (ZIP)* | creates an Agent Skill from the current settings |

The formats are described in [Profile format and profile code](design/profile-format.md) and
[Export as a skill](design/skill-export.md).

## Packaged profiles

The application contains 27 language-neutral profiles, among them 23 genre profiles (for example
*Official letter*, *News article*, *Fairy tale*) and the profiles *Casual*, *Comic style*,
*Academic social media post* and *Academic event report*. Four classic profiles are bound to the
original language of their authors: Goethe and E. T. A. Hoffmann (German), Mark Twain and Edgar
Wallace (English). Their targets were measured on public-domain texts; the sources are listed in
[PROVENANCE.md](../src/text_style_transfer/data/PROVENANCE.md). An operator can provide further
profiles through a read-only directory (see [Configuration](configuration.md)).

## History

The tab lists the runs of the current session with time, profile, path and length; each entry can be
shown again. The history is held in the memory of the session and ends with it.

## About

The tab shows the version, the host name of the language-model endpoint, a short statement on the
handling of texts, and the privacy notice of the operator if one is configured
(`TST_PRIVACY_NOTICE_FILE`).

## Limits

- Results are produced by a language model and can contain errors, omissions or additions. The checks
  are heuristics and detect only some of them.
- The application does not translate and does not check facts.
- The quality of the results depends on the model behind the endpoint. Smaller models follow strong
  settings and the rule against additions less reliably.
- The language examples and word lists for French, Spanish, Italian and Polish have not been reviewed
  by native speakers.
- The style descriptions of the classic profiles are interpretations.
- Profiles are not stored on the server. A profile that is not kept as a code or file is lost when the
  session ends.
