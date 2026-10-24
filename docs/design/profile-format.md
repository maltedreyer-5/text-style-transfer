# Profile format and profile code

## Profile JSON, version 1

```json
{
  "format": "text-style-profile",
  "version": 1,
  "name": "My style",
  "language": "de",
  "sliders": {"formal": 6, "funny": 3, "cefr_level": "B2"},
  "neutralization": {"enabled": true, "strength": "normal", "dimensions": ["tone", "register", "redundancy"]},
  "description": "…",
  "rules": ["…"],
  "metrics": {"sentence_length_mean": 18.2, "commas_per_sentence": 1.4, "personal_rate": 3.1, "words_measured": 640},
  "targets": {"sentence_length_mean": 15, "question_share": 0.1},
  "custom_sliders": [{"id": "custom_1", "type": "intensity", "label": "Rhymes", "instruction": "…"}],
  "origin": "analysis"
}
```

| Field | Content |
|---|---|
| `format`, `version` | required, with exactly the values shown |
| `language` | one of `en de fr es it pl`, or `null` for a profile that applies to every language |
| `sliders` | slider id → value: −10 to +10 for two poles (0 means inactive), 1 to 10 for intensity, a stage id for stages |
| `description` | at most 2,000 characters |
| `rules` | at most 12 rules of at most 300 characters each |
| `custom_sliders` | at most 5; ids of the form `custom_<n>`; type `intensity` or `polar`, the latter with `opposite_label` and `opposite_instruction` |
| `metrics` | values measured in the reference texts, with the keys of the metrics and indicator modules; a record that is not edited |
| `targets` | values the result is to approach: `sentence_length_mean` 3–80, `sentence_length_sd` 0–40, `sentences_per_paragraph` 1–30, `commas_per_sentence` 0–10, `question_share`, `exclamation_share` and `dialogue_share` 0–1; if the field is missing, the targets are taken from `metrics` |
| `labels`, `descriptions`, `id` | used by packaged profiles: names and descriptions per interface language, and the profile id |

A profile with a structural error (wrong type, format or version) is rejected. Errors in content, such
as an unknown slider, a value outside its range or a text that is too long, are corrected, and each
correction is reported.

## Profile code, version 1

```
tsp1.<base64url of the zlib-compressed canonical JSON>.<CRC-32 as 8 hex digits>
```

The canonical JSON has sorted keys, no spaces and UTF-8 encoding. Line breaks and spaces within a
pasted code are ignored. A code may have at most 24 KB and its JSON at most 64 KB; the second limit is
enforced during decompression. The checksum detects truncated and mistyped codes.

## Reasons

A code is a single line that can be stored in a note, an e-mail or a chat. It requires neither
storage on the server nor a user account.

The checksum does not identify the author of a code; any person can create a valid code. Since the
free text of a code (description, rules, own sliders) becomes part of the instructions to the model,
the interface shows it after the code is loaded.

## Limits

- Codes of other versions are rejected and are not converted.
- A profile refers to sliders by id. Settings for sliders that do not exist in the installed version
  are discarded, and the loss is reported.
