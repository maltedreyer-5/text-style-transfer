# Provenance of the classic profiles

The four classic profiles describe stylistic features in the project's own words. They contain no
quotations. Their `metrics` were measured with `text_style_transfer.core.metrics.measure()` on the
public-domain texts listed below, in their original language. The texts were retrieved from the
GITenberg mirrors of Project Gutenberg, used only for counting and not stored in this repository.
Paragraphs with fewer than four words and paragraphs in capital letters (headings) were skipped.

Inclusion rule: at least three public-domain works of at least 5,000 words each, in one of the six
supported text languages. Hans Christian Andersen was not included because his originals are Danish.

## Johann Wolfgang von Goethe (1749–1832): `goethe.json`

| Project Gutenberg eBook | Mirror | Words measured |
|---|---|---|
| #2403 | https://github.com/GITenberg/Die-Wahlverwandtschaften_2403 | 78,933 |
| #2335 | https://github.com/GITenberg/Wilhelm-Meisters-Lehrjahre-Band-1_2335 | 21,288 |
| #2407 | https://github.com/GITenberg/Die-Leiden-des-jungen-Werther---Band-1_2407 | 17,654 |
| #2404 | https://github.com/GITenberg/Italienische-Reise-Band-1_2404 | 106,810 |
| #2420 | https://github.com/GITenberg/Unterhaltungen-deutscher-Ausgewanderten_2420 | 13,659 |

## E. T. A. Hoffmann (1776–1822): `eta_hoffmann.json`

| Project Gutenberg eBook | Mirror | Words measured |
|---|---|---|
| #38780 | https://github.com/GITenberg/Lebensansichten-des-Katers-Murrnebst-fragmentarischer-Biographie-des-Kapellmeisters-Johannes-__38780 | 135,915 |
| #6341 | https://github.com/GITenberg/Nachtstucke_6341 | 105,699 |
| #9200 | https://github.com/GITenberg/Klein-Zaches-genannt-Zinnober-Ein-Marchen_9200 | 34,677 |

## Mark Twain (1835–1910): `mark_twain.json`

| Project Gutenberg eBook | Mirror | Words measured |
|---|---|---|
| #76 | https://github.com/GITenberg/Adventures-of-Huckleberry-Finn_76 | 111,499 |
| #74 | https://github.com/GITenberg/The-Adventures-of-Tom-Sawyer_74 | 70,881 |
| #3176 | https://github.com/GITenberg/The-Innocents-Abroad_3176 | 195,090 |

## Edgar Wallace (1875–1932): `edgar_wallace.json`

| Project Gutenberg eBook | Mirror | Words measured |
|---|---|---|
| #35545 | https://github.com/GITenberg/Sanders-of-the-River_35545 | 57,650 |
| #2688 | https://github.com/GITenberg/The-Clue-of-the-Twisted-Candle_2688 | 57,629 |
| #21530 | https://github.com/GITenberg/The-Angel-of-Terror_21530 | 62,687 |
| #20912 | https://github.com/GITenberg/The-Daffodil-Mystery_20912 | 67,680 |
| #24933 | https://github.com/GITenberg/The-Man-Who-Knew_24933 | 52,333 |

## Limits

- Sentence splitting is rule-based; abbreviations not listed in the language pack can split a sentence.
- Editions differ in punctuation and orthography from the first editions; the figures describe the
  measured editions.
- The style descriptions are interpretations of the authors' style; only the metrics are measured.
