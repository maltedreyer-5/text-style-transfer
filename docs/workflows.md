# Workflows

This chapter describes common tasks as sequences of steps. The names of tabs and controls are given
as they appear in the English interface. The German interface uses the following names:

| English | German |
|---|---|
| side bar *⚙️ Settings* | Seitenleiste *⚙️ Einstellungen* |
| *My style → skill* | *Mein Stil → Skill* |
| *Transform* | *Umschreiben* |
| *Copy a style* | *Stil kopieren* |
| *Refine* | *Verfeinern* |
| *Profile* | *Profil* |
| *History* | *Verlauf* |
| *About* | *Info* |

## Creating a skill from an own text

The tab *My style → skill* guides through this task in four steps. The result is a ZIP archive with
an Agent Skill that describes the writing style of the own text. The archive also contains the
profile from which the skill was made, so that the settings can be adjusted later.

1. Step *1 Text sample*: paste the own text into *Own text* or upload it as `.txt`, `.md` or `.docx`.
   Several texts are separated by a line that contains only `---`. Check *Text language*, enter
   *Name of the style* and select *Analyse style*.
2. The application counts the countable features of the text and passes the counts to the language
   model together with the text. The model returns slider values, a style description and up to five
   rules. The result becomes the own profile, the guided tab moves to step 2, and the side bar
   *⚙️ Settings* opens.
3. Step *2 Settings*: the step lists the sliders and measured targets set by the analysis. Notes of
   the form "the count contradicts it" name sliders whose value disagrees with an unambiguous count.
   Sliders and targets are adjusted in the side bar, where the areas that contain settings are open.
   *Show current settings as profile* updates the list. Description and rules are edited in this step
   and stored with *Apply to own profile*. Then select *Continue to try out*.
4. Step *3 Try out*: paste a test text of at least 40 words, preferably in a different style, and
   select *Style directly*. The table below the result compares source, target and result for each
   countable feature. After a further attempt, the previous result and its table are shown next to
   the current one. Adjust the settings in the side bar and repeat until the result matches the
   intended style. Then select *Continue to export*.
5. Step *4 Export*: select *Export as skill (ZIP)*. The archive is offered for download. The skill
   name is derived from *Name of the style*. *Create profile code* additionally provides the settings
   as a one-line code.
6. Install the skill as described in [Export as a skill](design/skill-export.md#installing-an-exported-skill).

The reference text is not part of the skill. To adjust the skill later, upload `profile.json` from
the skill folder in the tab *Profile* under *upload a profile JSON file*, change the settings and
export the skill again.

The same task can be carried out with the separate tabs *Copy a style*, *Transform*, *Refine* and
*Profile*. The guided tab uses the same settings and the same own profile as these tabs.

## Applying a packaged profile

1. In the tab *Transform*, enter or upload the text and check *Text language*.
2. In the side bar *⚙️ Settings*, choose a profile under *Profile*. The sliders, the neutralisation
   settings and, for classic profiles, the measured targets are set, and the areas that contain
   settings are opened. The text language remains unchanged.
3. Select *Neutralise, then style* or *Style directly*.
4. Read the result, the warnings and the table. Copy the result or export it under
   *Export result*.

## Neutralising a text

1. In the tab *Transform*, enter the text. In the side bar, choose the profile
   *– none (sliders only) –* and leave all sliders and targets inactive.
2. Under *Neutralisation* in the side bar, select the dimensions and the depth of intervention.
3. Select *Neutralise, then style*. Because no target style is set, the neutral text is the result.

## Keeping and passing on a profile

1. In the tab *Profile*, select *Create profile code*. The code is one line that starts with `tsp1.`.
   Alternatively, select *Download as JSON file*.
2. To restore the profile, paste the code under *Paste a profile code* and select *Load code*, or
   upload the JSON file.

A profile code or file received from another person can contain a description, rules and own
sliders. These texts become part of the instructions to the model and are shown after loading.

## Limits

- The analysis in the first workflow is carried out by the language model. Its slider
  values are judgements; the counts are evidence for some of them.
- Counting requires at least 40 words; sentence values require about 80 words and five sentences.
- Whether an installed skill is applied by Claude depends on the request and on the skill's
  description; this is not tested by the application.
