# SPDX-FileCopyrightText: 2026 Malte Dreyer
# SPDX-License-Identifier: MIT
import base64
import zlib

import pytest

from text_style_transfer.core import profile_code
from text_style_transfer.core.models import Profile
from text_style_transfer.core.profiles import ProfileError, profile_from_dict, profile_to_dict


def test_round_trip_via_code(catalog):
    profile = Profile(name="Mine", language="fr", sliders={"formal": 7, "cefr_level": "B1"},
                      description="Kurz.", rules=["Eins."])
    code = profile_code.encode(profile_to_dict(profile))
    assert code.startswith("tsp1.")
    again, issues = profile_from_dict(profile_code.decode(code), catalog.sliders)
    assert issues == []
    assert profile_to_dict(again) == profile_to_dict(profile)


def test_code_tolerates_line_breaks(catalog):
    code = profile_code.encode(profile_to_dict(Profile(name="x", sliders={"funny": 3})))
    broken = code[:20] + "\n  " + code[20:]
    assert profile_code.decode(broken)["sliders"] == {"funny": 3}


@pytest.mark.parametrize("code, error", [
    ("", "code_empty"),
    ("hello", "code_malformed"),
    ("tsp9.abc.00000000", "code_unsupported_version"),
    ("tsp1.!!!.00000000", "code_malformed"),
])
def test_code_rejects_garbage(code, error):
    with pytest.raises(profile_code.ProfileCodeError) as exc:
        profile_code.decode(code)
    assert exc.value.code == error


def test_code_detects_changed_payload():
    code = profile_code.encode({"format": "text-style-profile", "version": 1, "name": "x"})
    prefix, payload, crc = code.split(".")
    tampered = f"{prefix}.{payload}.{'0' * 8 if crc != '0' * 8 else '1' * 8}"
    with pytest.raises(profile_code.ProfileCodeError) as exc:
        profile_code.decode(tampered)
    assert exc.value.code == "code_checksum"


def test_code_rejects_decompression_bomb():
    bomb = zlib.compress(b"{" + b" " * (5 * 1024 * 1024) + b"}", 9)
    payload = base64.urlsafe_b64encode(bomb).decode().rstrip("=")
    assert len(payload) < profile_code.MAX_CODE_CHARS
    with pytest.raises(profile_code.ProfileCodeError) as exc:
        profile_code.decode(f"tsp1.{payload}.00000000")
    assert exc.value.code == "code_too_large"


def test_lenient_content_is_reported_not_silent(catalog):
    data = {"format": "text-style-profile", "version": 1, "name": "x",
            "sliders": {"formal": 42, "nope": 3, "cefr_level": "Z9", "funny": 0}}
    profile, issues = profile_from_dict(data, catalog.sliders)
    assert profile.sliders == {"formal": 10}
    codes = sorted(i.code for i in issues)
    assert codes == ["invalid_slider_value", "invalid_slider_value", "slider_value_clamped", "unknown_slider"]


@pytest.mark.parametrize("data, code", [
    ([], "profile_not_object"),
    ({"format": "other", "version": 1}, "profile_wrong_format"),
    ({"format": "text-style-profile", "version": 2}, "profile_wrong_version"),
    ({"format": "text-style-profile", "version": 1, "sliders": []}, "profile_field_type"),
])
def test_structural_errors_are_rejected(catalog, data, code):
    with pytest.raises(ProfileError) as exc:
        profile_from_dict(data, catalog.sliders)
    assert exc.value.code == code


def test_custom_sliders_travel_with_profile(catalog):
    data = {"format": "text-style-profile", "version": 1, "name": "x",
            "custom_sliders": [{"id": "custom_1", "type": "intensity", "label": "Rhymes",
                                "instruction": "Let sentence endings rhyme."}],
            "sliders": {"custom_1": 6}}
    profile, issues = profile_from_dict(data, catalog.sliders)
    assert issues == [] and profile.sliders == {"custom_1": 6}
