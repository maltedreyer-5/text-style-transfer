# SPDX-FileCopyrightText: 2026 Malte Dreyer
# SPDX-License-Identifier: MIT
"""Skill export: the published format rules and the content of SKILL.md."""
import copy
import io
import json
import re
import zipfile

import pytest
import yaml

from text_style_transfer.core import skill as skill_module
from text_style_transfer.core.models import Profile
from text_style_transfer.core.profiles import profile_from_dict
from text_style_transfer.core.skill import SkillError, build_skill, skill_name, write_zip


def front_matter(text: str) -> dict:
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    assert match, "SKILL.md must start with YAML front matter"
    return yaml.safe_load(match.group(1))


def assert_valid(export):
    """The rules of the published Agent Skills format."""
    md = export.files[f"{export.name}/SKILL.md"]
    meta = front_matter(md)
    assert set(meta) == {"name", "description"}
    assert meta["name"] == export.name
    assert len(meta["name"]) <= 64 and re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", meta["name"])
    assert "anthropic" not in meta["name"] and "claude" not in meta["name"]
    assert 0 < len(meta["description"]) <= 1024 and not set("<>") & set(meta["description"])
    assert sum(path.endswith("SKILL.md") for path in export.files) == 1
    return md, meta


def packaged(catalog, pid, lang="de"):
    profile = copy.deepcopy(catalog.profiles[pid])
    profile.description = profile.description_for(lang)
    return profile, profile.display_name(lang)


@pytest.mark.parametrize("name, expected", [
    ("Mein Stil: Test/1", "writing-style-mein-stil-test-1"),
    ("📄 Behördenbrief", "writing-style-behoerdenbrief"),
    ("Claude Anthropic", "writing-style"),
    ("My claude-like style", "writing-style-my-like-style"),
    ("", "writing-style"),
    ("a" * 70, "writing-style"),
    ("Größe " + "wort " * 30, "writing-style-groesse" + "-wort" * 8),
])
def test_skill_name_rules(name, expected):
    result = skill_name(name)
    assert result == expected
    assert len(result) <= 64


def test_classic_profile_skill(catalog):
    profile, display = packaged(catalog, "goethe")
    export = build_skill(profile, catalog, display)
    md, meta = assert_valid(export)
    assert export.name == "writing-style-goethe-klassische-prosa"
    assert "for texts in German" in meta["description"] and "Use when" in meta["description"]
    assert "📜" not in md.split("## Procedure")[0]
    body = md.split("---", 2)[2]
    assert body.index("FORMAL") < body.index("POETIC")              # strongest first
    assert "### German (Deutsch)" in body and "### French" not in body
    assert "Deutsche Prosa der Weimarer Klassik" in body            # description in the creator's language
    assert "## Measured targets" in body and "Average sentence length" in body
    assert "neutralise it in a working draft" in body                # the neutral path as a procedure
    assert export.issues == []


def test_language_neutral_profile_has_hints_for_all_languages(catalog):
    profile, display = packaged(catalog, "casual")
    export = build_skill(profile, catalog, display)
    md, _ = assert_valid(export)
    assert md.count("\n### ") == 6 and "Du-Anrede" in md and "tutoiement" in md


def test_profile_json_round_trip(catalog):
    profile, display = packaged(catalog, "official_letter")
    export = build_skill(profile, catalog, display)
    data = json.loads(export.files[f"{export.name}/profile.json"])
    again, issues = profile_from_dict(data, catalog.sliders)
    assert issues == [] and again.sliders == profile.sliders


def test_hostile_names_and_texts_stay_valid(catalog):
    profile = Profile(name="Claude <script>alert(1)</script> & “Anthropic”: Mein/Stil",
                      sliders={"funny": 4}, description="Use <b>bold</b> > and < signs.")
    md, meta = assert_valid(build_skill(profile, catalog))
    assert "<" not in meta["description"] and ">" not in meta["description"]


def test_length_rule_follows_slider(catalog):
    md = build_skill(Profile(name="x", sliders={"length": -5}), catalog).files["writing-style-x/SKILL.md"]
    assert "about 70 % as long" in md


def test_nothing_to_export(catalog):
    with pytest.raises(SkillError) as exc:
        build_skill(Profile(name="x"), catalog)
    assert exc.value.code == "skill_no_style"


def test_long_instructions_are_reported(catalog, monkeypatch):
    monkeypatch.setattr(skill_module, "BODY_TOKENS_RECOMMENDED", 100)
    export = build_skill(Profile(name="x", sliders={"funny": 4}), catalog)
    assert [i.code for i in export.issues] == ["skill_long"]


def test_zip_has_one_top_level_folder(catalog, tmp_path):
    export = build_skill(Profile(name="Mein Stil", sliders={"formal": 5}), catalog)
    path = write_zip(export, tmp_path)
    assert path.name == "writing-style-mein-stil.zip"
    with zipfile.ZipFile(io.BytesIO(path.read_bytes())) as archive:
        names = sorted(archive.namelist())
        assert names == ["writing-style-mein-stil/SKILL.md", "writing-style-mein-stil/profile.json"]
        assert archive.read(names[0]).decode().startswith("---\nname: writing-style-mein-stil\n")


@pytest.mark.parametrize("name, description", [
    ("claude-style", "ok"), ("my-anthropic-style", "ok"), ("Upper-case", "ok"), ("a--b", "ok"),
    ("-a", "ok"), ("a" * 65, "ok"), ("good-name", ""), ("good-name", "x" * 1025), ("good-name", "a <tag>"),
])
def test_validation_rejects_every_rule_violation(name, description):
    with pytest.raises(SkillError):
        skill_module.validate(name, description)
