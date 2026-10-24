# SPDX-FileCopyrightText: 2026 Malte Dreyer
# SPDX-License-Identifier: MIT
"""Starts the real application in a subprocess and talks to it over HTTP the
way the browser does. A socket guard in the subprocess refuses and records
every connection that does not go to the local machine."""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import textwrap
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import pytest
from fake_llm import FakeLLM

ROOT = Path(__file__).resolve().parents[1]

GUARD = textwrap.dedent('''
    import os, socket
    _LOG = os.environ["TST_TEST_GUARD_LOG"]
    _orig = socket.socket.connect
    def _check(addr):
        host = addr[0] if isinstance(addr, tuple) else addr
        if isinstance(host, str) and (host.startswith("127.") or host in ("::1", "localhost") or host.startswith("/")):
            return
        with open(_LOG, "a") as fh:
            fh.write(repr(addr) + "\\n")
        raise OSError("outbound connection blocked by test guard")
    def connect(self, addr):
        if self.family != socket.AF_UNIX:
            _check(addr)
        return _orig(self, addr)
    socket.socket.connect = connect
    _orig_gai = socket.getaddrinfo
    def getaddrinfo(host, *a, **k):
        if host not in (None, "localhost", "127.0.0.1", "::1", "0.0.0.0") and not str(host).startswith("127."):
            with open(_LOG, "a") as fh:
                fh.write("dns " + repr(host) + "\\n")
            raise socket.gaierror("blocked by test guard")
        return _orig_gai(host, *a, **k)
    socket.getaddrinfo = getaddrinfo
''')


def _start(env: dict, cwd: Path, log: Path, attempts: int = 3):
    """Start the application on a free port and wait until it answers.

    The port is chosen before the server binds it, so another process can take
    it in between; in that case the start is repeated with a new port.
    """
    for _ in range(attempts):
        port = _free_port()
        env = dict(env, TST_PORT=str(port))
        proc = subprocess.Popen([sys.executable, "-m", "text_style_transfer"], cwd=cwd, env=env,
                                stdout=open(log, "w"), stderr=subprocess.STDOUT)
        base = f"http://127.0.0.1:{port}"
        for _ in range(90):
            try:
                if _req(base + "/")[0] == 200:
                    return proc, base
            except OSError:
                pass
            if proc.poll() is not None:
                break
            time.sleep(1)
        proc.terminate()
        proc.wait(20)
        if "Cannot find empty port" not in log.read_text():
            raise AssertionError(log.read_text())
    raise AssertionError("no free port after several attempts")


def _snapshot(folder: Path) -> dict[str, float]:
    return {str(p): p.stat().st_mtime for p in folder.rglob("*") if p.is_file() and "__pycache__" not in p.parts}


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _req(url, data=None, headers=None):
    request = urllib.request.Request(url, data=data, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=20) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read()


class App:
    def __init__(self, base: str) -> None:
        self.base = base
        self.config = json.loads(_req(base + "/config")[2])
        self.components = {c["id"]: c for c in self.config["components"]}

    def dep(self, name: str) -> dict:
        return next(d for d in self.config["dependencies"] if d.get("api_name") == name)

    def defaults(self, dep: dict) -> list:
        return [self.components[i].get("props", {}).get("value") for i in dep["inputs"]]

    def call(self, name: str, overrides: dict[int, object], session: str, headers: dict | None = None) -> list:
        dep = self.dep(name)
        data = self.defaults(dep)
        for index, value in overrides.items():
            data[index] = value
        body = json.dumps({"data": data, "fn_index": dep["id"], "session_hash": session,
                           "event_data": None, "trigger_id": None}).encode()
        status, _, raw = _req(self.base + "/gradio_api/queue/join", body,
                              {"Content-Type": "application/json", **(headers or {})})
        assert status == 200, raw
        stream = urllib.request.urlopen(f"{self.base}/gradio_api/queue/data?session_hash={session}", timeout=60)
        for line in stream:
            line = line.decode().strip()
            if line.startswith("data:"):
                msg = json.loads(line[5:])
                if msg.get("msg") == "process_completed":
                    assert msg.get("success", True), msg
                    return msg["output"]["data"]
        raise AssertionError("no result")


@pytest.fixture(scope="module")
def app(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("app")
    workdir = tmp / "workdir"
    workdir.mkdir()
    (tmp / "sitecustomize.py").write_text(GUARD)
    guard_log = tmp / "guard.log"
    guard_log.write_text("")
    with FakeLLM() as fake:
        env = {k: v for k, v in os.environ.items() if not k.startswith("TST_")}
        env.update({
            "PYTHONPATH": os.pathsep.join([str(tmp), str(ROOT / "src")]),
            "TMPDIR": str(tmp), "TST_TEST_GUARD_LOG": str(guard_log),
            "TST_LLM_BASE_URL": fake.url, "TST_LLM_RETRY_DELAY": "0",
            "TST_MAX_UPLOAD": "200kb", "PYTHONDONTWRITEBYTECODE": "1",
        })
        package_before = _snapshot(ROOT / "src")
        proc, base = _start(env, workdir, tmp / "app.log")
        try:
            yield App(base), tmp, guard_log, fake
        finally:
            proc.terminate()
            proc.wait(20)
        # Invariant: the application writes neither into its working directory
        # nor into its package; and its log contains no user texts.
        assert list(workdir.iterdir()) == []
        assert _snapshot(ROOT / "src") == package_before
        log = (tmp / "app.log").read_text()
        assert "Ausschuss" not in log and "Personal content" not in log


def test_privacy_defaults(app):
    a, *_ = app
    assert a.config.get("run_history") is False
    assert a.config.get("footer_links") == ["gradio", "settings"]
    assert a.config.get("max_file_size") == 200 * 1024
    assert _req(a.base + "/monitoring")[0] == 403
    info = json.loads(_req(a.base + "/gradio_api/info")[2])
    assert info.get("named_endpoints") == {}
    status, headers, _ = _req(a.base + "/")
    lowered = {k.lower(): v for k, v in headers.items()}
    assert lowered.get("x-frame-options") == "DENY"
    assert "frame-ancestors 'none'" in lowered.get("content-security-policy", "")
    assert "set-cookie" not in lowered


def test_upload_is_deleted_after_reading(app):
    a, *_ = app
    boundary = "----tst"
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"files\"; filename=\"in.txt\"\r\n"
            f"Content-Type: text/plain\r\n\r\nPersonal content\r\n--{boundary}--\r\n").encode()
    status, _, raw = _req(a.base + "/gradio_api/upload", body, {"Content-Type": f"multipart/form-data; boundary={boundary}"})
    path = json.loads(raw)[0]
    assert Path(path).exists()
    file_data = {"path": path, "meta": {"_type": "gradio.FileData"}, "orig_name": "in.txt"}
    out = a.call("on_upload", {0: file_data, 1: "en"}, uuid.uuid4().hex)
    assert out[0] == "Personal content"
    assert not Path(path).exists()


def test_run_isolation_and_no_outbound(app):
    a, tmp, guard_log, fake = app
    dep = a.dep("run_1")  # second run handler: "style directly"
    ids = dep["inputs"]
    source = "Der Ausschuss hat am Montag beschlossen, den Plan mit 3,5 Millionen Euro zu fördern. " * 3
    overrides = {0: source, 2: "de", 3: "builtin:casual", len(ids) - 1: "de"}
    session_a, session_b = uuid.uuid4().hex, uuid.uuid4().hex
    out = a.call("run_1", overrides, session_a)
    assert out[0] == source.strip().upper()
    assert "Fertig" in out[3]                      # server-side message in the browser's language
    system = fake.requests[-1]["messages"][0]["content"]
    assert "Write your entire answer in German" in system
    assert "Entspannter Alltagston" in system      # profile description in the UI language

    show = a.dep("do_history_show")
    assert a.call("do_history_show", {0: 1, len(show["inputs"]) - 1: "en"}, session_a)[0] == source
    other = a.call("do_history_show", {0: 1, len(show["inputs"]) - 1: "en"}, session_b)
    assert other[0] == "" and "no entry" in other[1]
    assert guard_log.read_text() == "", guard_log.read_text()


def test_guard_blocks_outbound(tmp_path):
    """Negative control: without it, an empty guard log would prove nothing."""
    (tmp_path / "sitecustomize.py").write_text(GUARD)
    log = tmp_path / "guard.log"
    log.write_text("")
    env = dict(os.environ, PYTHONPATH=str(tmp_path), TST_TEST_GUARD_LOG=str(log))
    code = "import urllib.request\ntry:\n    urllib.request.urlopen('http://example.org', timeout=3)\nexcept Exception:\n    pass\n"
    subprocess.run([sys.executable, "-c", code], env=env, check=True, timeout=30)
    assert "example.org" in log.read_text()


def test_sigterm_removes_temporary_directory(tmp_path):
    """docker stop and systemd send SIGTERM; the regular shutdown must still run."""
    import signal

    env = {k: v for k, v in os.environ.items() if not k.startswith("TST_")}
    env.update({"PYTHONPATH": str(ROOT / "src"), "TMPDIR": str(tmp_path)})
    log = tmp_path / "app.log"
    proc, _base = _start(env, tmp_path, log)
    assert list(tmp_path.glob("text-style-transfer-*")), sorted(p.name for p in tmp_path.iterdir())
    proc.send_signal(signal.SIGTERM)
    code = proc.wait(30)
    assert code == 0, f"exit code {code}\n{log.read_text()}"
    left = list(tmp_path.glob("text-style-transfer-*"))
    assert not left, f"{left}\n{log.read_text()}"


def test_language_falls_back_to_accept_language(app):
    """If the browser reports no language, the header decides, and the result is stored
    for all later events of the session."""
    a, *_ = app
    out = a.call("on_load", {0: ""}, uuid.uuid4().hex, {"Accept-Language": "de-DE,de;q=0.9"})
    assert out[0] == "de"
    out = a.call("on_load", {0: ""}, uuid.uuid4().hex, {"Accept-Language": "fr-FR"})
    assert out[0] == "en"          # no French interface: English


def test_text_language_follows_browser_not_profile(app):
    a, *_ = app
    out = a.call("on_load", {0: ""}, uuid.uuid4().hex, {"Accept-Language": "fr-FR"})
    assert out[0] == "en" and out[1]["value"] == "fr"   # English interface, French texts
    language_ids = {c["id"] for c in a.config["components"]
                    if "common.text_language" in str(c.get("props", {}).get("label", ""))}
    assert len(language_ids) == 4                         # transform, copy, refine, guided tab
    for dep in a.config["dependencies"]:
        if str(dep.get("api_name", "")).startswith("apply_profile"):
            assert not language_ids & set(dep["outputs"])


def test_moving_a_slider_activates_it(app):
    a, *_ = app
    checkboxes = {c["id"] for c in a.config["components"] if c["type"] == "checkbox"
                  and "common.active" in str(c.get("props", {}).get("label", ""))}
    activating = [d for d in a.config["dependencies"]
                  if [t[1] for t in d.get("targets", [])] == ["input"] and len(d["outputs"]) == 1
                  and d["outputs"][0] in checkboxes]
    from text_style_transfer.ui.app import TARGET_FIELDS

    expected = 34 + len(TARGET_FIELDS)            # sliders and targets
    assert len(checkboxes) == expected and len(activating) == expected


def test_choice_values_are_ids_not_labels(app):
    """Invariant 1: what users see is never what the code compares.

    File extensions are the one deliberate exception: they are shown as they
    are and are never translated."""
    from text_style_transfer.core.documents import EXPORT_FORMATS

    a, *_ = app
    ident = re.compile(r"^[A-Za-z0-9_:.-]+$")
    checked = 0
    for comp in a.config["components"]:
        for choice in comp.get("props", {}).get("choices") or []:
            label, value = choice
            if isinstance(value, str):
                assert ident.match(value), value
                assert value != label or value in EXPORT_FORMATS, value
                checked += 1
    assert checked > 50


def test_skill_export_through_the_interface(app):
    a, *_ = app
    import zipfile as _zip

    dep = a.dep("do_skill")
    last = len(dep["inputs"]) - 1
    session = uuid.uuid4().hex
    out = a.call("do_skill", {0: "Mein Stil", 1: "builtin:casual", last: "de"}, session)
    assert "writing-style-mein-stil" in out[1]
    with _zip.ZipFile(out[0]["path"]) as archive:
        assert sorted(archive.namelist()) == ["writing-style-mein-stil/SKILL.md", "writing-style-mein-stil/profile.json"]
    out = a.call("do_skill", {0: "", 1: "none", last: "de"}, session)
    assert out[0] is None and "nichts zu exportieren" in out[1]


def test_targets_editor_and_measurements(app):
    """Points 1, 2 and 5: targets are preset from a profile, a run shows source/target/result,
    description and rules can be edited."""
    a, *_ = app
    session = uuid.uuid4().hex
    applied = a.call("apply_profile", {0: "builtin:goethe", 2: "de"}, session)
    from text_style_transfer.ui.app import TARGET_FIELDS

    first_target = 68                               # target fields follow the 34 slider pairs
    assert applied[first_target]["value"] is True   # sentence length target switched on
    assert abs(applied[first_target + 1]["value"] - 22.4) < 0.1
    assert "Weimarer Klassik" in applied[-3] and applied[-2] == ""

    dep = a.dep("do_apply_text")
    out = a.call("do_apply_text", {0: "Kurze, klare Sätze.", 1: "Regel eins\n\nRegel zwei", 2: "builtin:goethe",
                                   len(dep["inputs"]) - 1: "de"}, session)
    assert "übernommen" in out[0]
    shown = a.call("apply_profile", {0: "session", 2: "de"}, session)
    assert shown[-3] == "Kurze, klare Sätze." and shown[-2] == "Regel eins\nRegel zwei"

    run = a.dep("run_1")
    source = ("Wir haben am Montag beschlossen, den Plan zu prüfen. Ich denke, du hast recht. " * 6).strip()
    values = {0: source, 2: "de", 3: "builtin:casual", len(run["inputs"]) - 1: "de"}
    t0 = 7 + 68                                    # first target field in the run inputs
    values[t0] = True
    values[t0 + 1] = 30                            # target: 30 words per sentence
    out = a.call("run_1", values, session)
    assert "| Wörter pro Satz |" in out[6] and "| 30,0 |" in out[6]
    assert "Wörter pro Satz: Ziel 30,0" in out[2]  # the result (about 8 words) misses the target
    assert len(TARGET_FIELDS) == 7


def _value(update, old):
    return update["value"] if isinstance(update, dict) and "value" in update else (old if isinstance(update, dict) else update)


def test_own_text_to_skill_keeps_adjustments(app):
    """The workflow "own text -> adjust -> skill", with the interface state carried between steps
    as the browser does. Adjustments made after the analysis must reach the skill."""
    import zipfile as _zip

    from text_style_transfer.core.catalog import load_catalog
    from text_style_transfer.ui.app import TARGET_FIELDS

    a, *_ = app
    sids = list(load_catalog().sliders)
    ns, nt = 2 * len(sids), 2 * len(TARGET_FIELDS)
    session = uuid.uuid4().hex
    ui = a.defaults(a.dep("run_1"))[7:7 + ns + nt]
    own = ("Ich schreibe, wie ich rede. Kurz. Direkt. Du kennst das bestimmt. Warum? Weil es so ist. " * 10).strip()
    out = a.call("do_analyze", {0: own, 1: "de", 2: "Mein Stil", 4: "de"}, session)
    assert "Weiter:" in out[0]
    applied = a.call("apply_profile_1", {0: "session", 2: "de"}, session)
    ui = [_value(u, old) for u, old in zip(applied[:ns + nt], ui, strict=True)]
    i = sids.index("formal")
    ui[2 * i], ui[2 * i + 1] = True, -6          # the person corrects the analysis
    ui[ns], ui[ns + 1] = True, 9.0               # and sets 9 words per sentence

    dep = a.dep("do_apply_text")
    values = {0: "Kurz und direkt.", 1: "Frag die Leserin.", 2: "session", len(dep["inputs"]) - 1: "de"}
    values.update({6 + k: v for k, v in enumerate(ui)})
    a.call("do_apply_text", values, session)
    applied = a.call("apply_profile_1", {0: "session", 2: "de"}, session)
    assert _value(applied[2 * i + 1], None) == -6 and _value(applied[ns + 1], None) == 9.0

    dep = a.dep("do_skill")
    values = {0: "Mein Stil", 1: "session", len(dep["inputs"]) - 1: "de"}
    values.update({5 + k: _value(u, old) for k, (u, old) in enumerate(zip(applied[:ns + nt], ui, strict=True))})
    out = a.call("do_skill", values, session)
    with _zip.ZipFile(out[0]["path"]) as archive:
        md = archive.read("writing-style-mein-stil/SKILL.md").decode()
    assert "INFORMAL (clear, 6/10)" in md and "about 9 words" in md and "Frag die Leserin." in md


def test_profile_without_targets_leaves_target_fields_alone(app):
    """A profile without targets must not write a nested update into the target fields
    (the next run would fail while reading them)."""
    a, *_ = app
    applied = a.call("apply_profile", {0: "builtin:casual", 2: "de"}, uuid.uuid4().hex)
    target_values = applied[68 + 1:68 + 14:2]
    assert all(isinstance(u, dict) and "value" not in u for u in target_values)


def test_guided_tab_from_own_text_to_skill(app):
    """The guided tab: analysis moves to step 2 and opens the side bar, the profile sets and opens
    the areas with settings, two runs show the previous attempt, and the export uses the one name."""
    import zipfile as _zip

    from text_style_transfer.core.catalog import load_catalog
    from text_style_transfer.ui.app import TARGET_FIELDS

    a, *_ = app
    names = [d.get("api_name") for d in a.config["dependencies"]]
    apply_after_wizard = next(n for n in names[names.index("wiz_analyze_fn"):] if str(n).startswith("apply_profile"))
    sids = list(load_catalog().sliders)
    ns, nt = 2 * len(sids), 2 * len(TARGET_FIELDS)
    session = uuid.uuid4().hex
    own = ("Ich schreibe, wie ich rede. Kurz. Direkt. Du kennst das bestimmt. Warum? Weil es so ist. " * 10).strip()

    out = a.call("wiz_analyze_fn", {0: own, 1: "de", 2: "Mein Stil", 4: "de"}, session)
    assert "Schritt 2" in out[0]
    assert out[3].get("selected") == 1 and out[4].get("open") is True
    applied = a.call(apply_after_wizard, {0: "session", 2: "de"}, session)
    opened = applied[ns + nt + 4:ns + nt + 4 + 9]          # sliders area, seven groups, targets area
    assert opened[0].get("open") is True and opened[-1].get("open") is True
    assert sum(1 for u in opened[1:-1] if u.get("open") is True) >= 1
    ui = [_value(u, old) for u, old in zip(applied[:ns + nt], a.defaults(a.dep("run_1"))[7:7 + ns + nt], strict=True)]

    run = a.dep("run_2")                                   # guided tab, "Style directly"
    test = ("Die Geschäftsleitung hat beschlossen, die Befragung auf das dritte Quartal zu verschieben. " * 6).strip()
    values = {0: test, 1: "de", 2: "session", len(run["inputs"]) - 1: "de"}
    values.update({6 + k: v for k, v in enumerate(ui)})
    first = a.call("run_2", values, session)
    second = a.call("run_2", values, session)
    assert first[0] and second[5] == first[0]              # previous attempt is shown next to the result
    assert "| Wörter pro Satz |" in second[4]

    dep = a.dep("do_skill_1")
    values = {0: "Mein Stil", 1: "session", len(dep["inputs"]) - 1: "de"}
    values.update({5 + k: v for k, v in enumerate(ui)})
    out = a.call("do_skill_1", values, session)
    with _zip.ZipFile(out[0]["path"]) as archive:
        assert "writing-style-mein-stil/SKILL.md" in archive.namelist()


@pytest.mark.parametrize("delay", [0.5, 1.5, 2.5])
def test_sigterm_during_start_up_ends_cleanly(tmp_path, delay):
    """A stop signal at any moment of the start must not leave a traceback or temporary files.

    Before the handler is installed the process ends with the default signal code (-15) and has
    created nothing; afterwards it ends with exit code 0.
    """
    import signal

    env = {k: v for k, v in os.environ.items() if not k.startswith("TST_")}
    env.update({"PYTHONPATH": str(ROOT / "src"), "TMPDIR": str(tmp_path), "TST_PORT": str(_free_port())})
    proc = subprocess.Popen([sys.executable, "-m", "text_style_transfer"], cwd=tmp_path, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    time.sleep(delay)
    proc.send_signal(signal.SIGTERM)
    code = proc.wait(30)
    errors = proc.stderr.read().decode()
    assert code in (0, -signal.SIGTERM), f"exit code {code}\n{errors}"
    assert "Traceback" not in errors, errors
    assert not list(tmp_path.glob("text-style-transfer-*"))


def test_guided_tab_remaining_functions(app):
    """Step 2 (refresh, edit), step 3 (neutral path), step 4 (profile code) and the navigation."""
    from text_style_transfer.core.catalog import load_catalog
    from text_style_transfer.ui.app import TARGET_FIELDS

    a, *_ = app
    names = [d.get("api_name") for d in a.config["dependencies"]]
    after = names[names.index("wiz_analyze_fn"):]
    apply_name = next(n for n in after if str(n).startswith("apply_profile"))
    refresh, apply_text = next(n for n in after if str(n).startswith("do_summary")), next(n for n in after if str(n).startswith("do_apply_text"))
    code = next(n for n in after if str(n).startswith("do_code"))
    neutral_run = [n for n in after if str(n).startswith("run_")][1]          # second run of the guided tab
    navigation = [n for n in after if str(n).startswith("go")]                 # next2, next3, back2, back3, back4
    ns, nt = 2 * len(load_catalog().sliders), 2 * len(TARGET_FIELDS)
    session = uuid.uuid4().hex
    own = ("Ich schreibe, wie ich rede. Kurz. Direkt. Du kennst das bestimmt. Warum? Weil es so ist. " * 10).strip()
    a.call("wiz_analyze_fn", {0: own, 1: "de", 2: "Mein Stil", 4: "de"}, session)
    applied = a.call(apply_name, {0: "session", 2: "de"}, session)
    ui = [_value(u, old) for u, old in zip(applied[:ns + nt], a.defaults(a.dep("run_1"))[7:7 + ns + nt], strict=True)]

    def with_ui(name, offset, fixed):
        values = dict(fixed)
        values.update({offset + k: v for k, v in enumerate(ui)})
        values[len(a.dep(name)["inputs"]) - 1] = "de"
        return values

    assert "**Ziele:**" in a.call(refresh, with_ui(refresh, 4, {0: "session"}), session)[0]
    out = a.call(apply_text, with_ui(apply_text, 6, {0: "Kurz.", 1: "Frag nach.", 2: "session"}), session)
    assert "übernommen" in out[0]
    test = ("Die Geschäftsleitung hat beschlossen, die Befragung auf das dritte Quartal zu verschieben. " * 6).strip()
    out = a.call(neutral_run, with_ui(neutral_run, 6, {0: test, 1: "de", 2: "session"}), session)
    assert out[0] and "✅" in out[2]
    assert a.call(code, with_ui(code, 5, {0: "Mein Stil", 1: "session"}), session)[0].startswith("tsp1.")
    steps = [a.call(n, {}, session) for n in navigation]
    assert [s[0].get("selected") for s in steps] == [2, 3, 0, 1, 2]
    assert steps[3][1].get("open") is True                                     # back to settings opens the side bar
