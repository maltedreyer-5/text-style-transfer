# SPDX-FileCopyrightText: 2026 Malte Dreyer
# SPDX-License-Identifier: MIT
"""Consistency of the packaged data and the UI catalogs."""
import ast
from pathlib import Path

from text_style_transfer.core.models import TEXT_LANGUAGES, UI_LANGUAGES
from text_style_transfer.i18n import data_keys, load_ui_catalogs, placeholders

SRC = Path(__file__).resolve().parents[1] / "src" / "text_style_transfer"


def test_catalog_complete(catalog):
    assert len(catalog.sliders) == 34
    assert set(catalog.languages) == set(TEXT_LANGUAGES)
    assert {"casual", "goethe", "eta_hoffmann", "mark_twain", "edgar_wallace"} <= set(catalog.profiles)
    for pid in ("goethe", "eta_hoffmann", "mark_twain", "edgar_wallace"):
        assert catalog.profiles[pid].language in ("de", "en")
        assert catalog.profiles[pid].metrics["words_measured"] > 15000


def test_every_language_pack_has_every_example(catalog):
    for pack in catalog.languages.values():
        assert set(pack.examples) == set(catalog.example_keys)
        assert all(v.strip() for v in pack.examples.values())


def test_ui_catalogs_have_same_keys_and_placeholders(catalog):
    cats = load_ui_catalogs()
    assert set(cats["en"]) == set(cats["de"])
    for key in cats["en"]:
        assert placeholders(cats["en"][key]) == placeholders(cats["de"][key]), key
    derived = data_keys(catalog)
    assert set(derived["en"]) == set(derived["de"])


def test_every_issue_code_has_a_message():
    cats = load_ui_catalogs()
    codes = set()
    for path in SRC.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and getattr(node.func, "id", getattr(node.func, "attr", "")) in (
                    "Issue", "PipelineError", "LLMError", "DocumentError", "ProfileError", "ProfileCodeError"):
                if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                    codes.add(node.args[0].value)
    missing = sorted(c for c in codes if f"issue.{c}" not in cats["en"])
    assert not missing, missing


def test_static_labels_exist():
    cats = load_ui_catalogs()
    tree = ast.parse((SRC / "ui" / "app.py").read_text(encoding="utf-8"))
    keys = {n.args[0].value for n in ast.walk(tree)
            if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "I"
            and n.args and isinstance(n.args[0], ast.Constant)}
    derived_prefixes = ("slider.", "stage.", "group.", "profile.library.", "conflict.")
    missing = [k for k in keys if k not in cats["en"] and not k.startswith(derived_prefixes)
               and not (k.startswith("profile.") and k.split(".", 1)[1] not in ("none", "session"))]
    assert not missing, missing


def test_i18n_objects_are_never_formatted_or_joined():
    """gr.I18n placeholders silently ignore .format() and only the first
    placeholder of a string is translated (see i18n.py)."""
    tree = ast.parse((SRC / "ui" / "app.py").read_text(encoding="utf-8"))

    def is_i18n(node):
        return isinstance(node, ast.Call) and getattr(node.func, "id", "") in ("I", "i18n")

    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            assert not is_i18n(node.value), f"attribute on I18n object at line {node.lineno}"
        if isinstance(node, ast.BinOp):
            parts = [node.left, node.right]
            assert sum(map(is_i18n, parts)) < 2, f"two I18n objects joined at line {node.lineno}"
            assert not (is_i18n(node.right) and not is_i18n(node.left)), \
                f"I18n object not at the start of a string at line {node.lineno}"


def test_ui_languages():
    assert UI_LANGUAGES == ("en", "de")


def test_profile_directory(tmp_path):
    import json

    import pytest
    from text_style_transfer.config import Config
    from text_style_transfer.core.catalog import CatalogError
    from text_style_transfer.ui.app import build_services

    profile = {"format": "text-style-profile", "version": 1, "name": "House style",
               "labels": {"en": "House style", "de": "Hausstil"}, "sliders": {"formal": 4}}
    (tmp_path / "house_style.json").write_text(json.dumps(profile), encoding="utf-8")
    svc = build_services(Config.from_env({"TST_PROFILE_DIR": str(tmp_path)}))
    assert svc.library["house_style"].sliders == {"formal": 4}
    assert svc.tr.t("profile.library.house_style", "de") == "Hausstil"
    assert not list(tmp_path.glob("*.tmp")) and sorted(p.name for p in tmp_path.iterdir()) == ["house_style.json"]

    (tmp_path / "broken.json").write_text(json.dumps({**profile, "sliders": {"nope": 1}}), encoding="utf-8")
    with pytest.raises(CatalogError, match="broken.json"):
        build_services(Config.from_env({"TST_PROFILE_DIR": str(tmp_path)}))
    (tmp_path / "broken.json").unlink()
    (tmp_path / "Bad Name.json").write_text(json.dumps(profile), encoding="utf-8")
    with pytest.raises(CatalogError, match="file name"):
        build_services(Config.from_env({"TST_PROFILE_DIR": str(tmp_path)}))


def test_language_names_in_messages():
    from text_style_transfer.core.models import Issue
    from text_style_transfer.i18n import Translator

    tr = Translator(load_ui_catalogs())
    text = tr.issue(Issue("input_language_mismatch", {"expected": "de", "found": "en"}), "de")
    assert "Englisch" in text and "Deutsch" in text and "{" not in text


def test_measurement_labels_and_number_format():
    from text_style_transfer.core.models import Issue
    from text_style_transfer.i18n import Translator
    from text_style_transfer.ui.app import MEASURE_ROWS, TARGET_FIELDS

    cats = load_ui_catalogs()
    for key in {k for k, *_ in TARGET_FIELDS} | {k for k, _ in MEASURE_ROWS}:
        assert f"measure.{key}" in cats["en"], key
    tr = Translator(cats)
    text = tr.issue(Issue("check_target", {"metric": "sentence_length_mean", "target": 14.0, "actual": 22.35}), "de")
    assert text == "Wörter pro Satz: Ziel 14,0, Ergebnis 22,4."
