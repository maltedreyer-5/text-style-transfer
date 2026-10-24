# Languages: interface and text

## Two independent languages

The application distinguishes the text language, in which the model reads and writes, from the
interface language, in which labels and messages appear. Six text languages and two interface
languages are supported. The two settings are independent, so that the language of a text is not
bound to the language of the person who uses the tool.

## Instructions to the model

The instructions to the model are written in English and are identical for all text languages. Each
text language has a language pack that contributes the language-specific parts:

- example words for 16 features whose expression depends on the language, among them forms of
  address (*Sie/du*, *vous/tu*, *usted/tú*, *Lei/tu*, *Pan/ty*), passive constructions, hedging and
  nominal style;
- quotation marks, decimal separators and group separators;
- patterns for introductory and closing remarks that models add to their answers;
- function words, used to detect the language of a text;
- abbreviations, used for sentence splitting;
- word lists for countable features: personal pronouns, formal and familiar forms of address (for
  English, contractions serve as familiar marker), hedging words, and a pattern for nominalisation
  suffixes.

A single set of instructions is maintained in one place. Six translated sets would contain the same
logic six times and would diverge over time.

## Interface texts

Static labels are translated in the browser by Gradio's `I18n` component. Messages with parameters are
formatted on the server in the language the browser reported when the page was loaded. Two properties
of `I18n` are covered by tests: calling `.format()` on an `I18n` object returns the untranslated
placeholder without an error, and only the first placeholder within a string is translated.

Descriptions and rules that the model writes for a new profile are in the interface language of the
person who creates the profile. Packaged profiles contain their description in English and German.

## Limits

- The language examples and word lists for French, Spanish, Italian and Polish have not been reviewed
  by native speakers.
- Gradio provides no Italian translation of its own interface texts, for example of the upload field.
  This matters only if an Italian interface is added.
- After the interface language is changed in Gradio's settings, server messages follow after the page
  is reloaded.
- Some messages are produced by Gradio and appear in English, for example for an upload that is too
  large or of a type the field does not accept.
- The language check is based on function-word frequencies and runs for texts of 30 words or more.
- The countable features are word counts. Pronouns attached to verbs (Spanish *enviarme*, Italian
  *inviarmi*) are not counted. Formal forms that also occur as ordinary words, such as German *Sie* at
  the beginning of a sentence or Polish *pan* in lower case, are counted only where they are
  unambiguous. Passive voice is not counted. The application derives no norm values from the counts;
  the checks compare source and result.
