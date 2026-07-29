"""Tests for the GitHub-Releases auto-updater.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import json

from khervebook import updater


def test_parse_version_drops_the_build_sha():
    assert updater.parse_version("v0.1.137+a6cf9dd") == (0, 1, 137)
    assert updater.parse_version("0.1.137") == (0, 1, 137)
    assert updater.parse_version("") == ()


def test_is_newer_compares_numerically_not_lexically():
    # The bug a string compare would introduce: "0.1.9" > "0.1.137".
    assert updater.is_newer("0.1.137", "0.1.9")
    assert not updater.is_newer("0.1.9", "0.1.137")
    assert not updater.is_newer("0.1.137", "0.1.137+abc1234")
    assert updater.is_newer("0.2.0", "0.1.999")
    # Unparseable input must never look like an update.
    assert not updater.is_newer("", "0.1.1")


def test_shorter_version_is_not_newer_than_its_own_point_release():
    assert not updater.is_newer("0.1", "0.1.5")
    assert updater.is_newer("0.2", "0.1.5")


def test_pick_asset_prefers_the_version_stamped_installer(monkeypatch):
    monkeypatch.setattr(updater.os, "name", "nt")
    release = {"assets": [
        {"name": "KherveBook-0.1.140-portable.zip",
         "browser_download_url": "https://x/zip"},
        {"name": "KherveBook-Setup.exe", "browser_download_url": "https://x/s"},
        {"name": "KherveBook-Setup-0.1.140.exe",
         "browser_download_url": "https://x/v"},
    ]}
    assert updater._pick_asset(release) == "https://x/v"


def test_pick_asset_falls_back_to_the_release_page():
    release = {"assets": [], "html_url": "https://github.com/x/releases/tag/v1"}
    assert updater._pick_asset(release) == release["html_url"]


def test_check_latest_reads_the_github_release(monkeypatch):
    payload = {"tag_name": "v0.1.140",
               "html_url": "https://github.com/gkerherve/KherveBook/tag",
               "body": "## What's new\n- Sheet cells got faster\n",
               "assets": [{"name": "KherveBook-Setup-0.1.140.exe",
                           "browser_download_url": "https://x/setup.exe"}]}
    monkeypatch.setattr(updater.os, "name", "nt")
    monkeypatch.setattr(updater, "_get",
                        lambda url, **kw: json.dumps(payload).encode())
    result = updater.check_latest()
    assert result["version"] == "0.1.140"
    assert result["url"] == "https://x/setup.exe"
    assert "Sheet cells got faster" in result["notes"]


def test_check_latest_reports_the_error_when_offline(monkeypatch):
    def boom(url, **kw):
        raise OSError("no network")
    monkeypatch.setattr(updater, "_get", boom)
    assert "no network" in updater.check_latest()["error"]


def test_notes_stop_at_the_horizontal_rule():
    html = updater.notes_to_html(
        "## Highlights\n- A thing\n\n---\n\nDownload and run the installer.")
    assert "A thing" in html
    assert "Download and run" not in html


def test_notes_render_headings_bullets_and_marks():
    html = updater.notes_to_html(
        "# Title\nSome **bold** prose.\n- one\n- two `code`\n")
    assert "<h3>Title</h3>" in html
    assert "<b>bold</b>" in html
    assert html.count("<li>") == 2
    assert "<code>code</code>" in html


def test_notes_fold_wrapped_bullet_continuations():
    html = updater.notes_to_html("- a bullet that\n  wraps over two lines\n")
    assert "<li>a bullet that wraps over two lines</li>" in html


def test_notes_escape_html_in_the_release_body():
    assert "&lt;script&gt;" in updater.notes_to_html("- <script>")


def test_source_checkouts_never_self_update(monkeypatch):
    monkeypatch.delenv("KHERVEBOOK_UPDATE_TEST_EXE", raising=False)
    monkeypatch.setattr(updater, "_is_frozen", lambda: False)
    assert not updater.can_self_update()


def test_portable_copies_never_self_update(monkeypatch):
    """No registry InstallDir, or one pointing elsewhere: a silent install
    would upgrade a different copy and reopen the wrong exe."""
    monkeypatch.setattr(updater.os, "name", "nt")
    monkeypatch.setattr(updater, "_is_frozen", lambda: True)
    monkeypatch.setattr(updater, "app_exe",
                        lambda: r"D:\portable\KherveBook\KherveBook.exe")
    monkeypatch.setattr(updater, "_registered_install_dir", lambda: "")
    assert not updater.can_self_update()
    monkeypatch.setattr(updater, "_registered_install_dir",
                        lambda: r"C:\Users\me\Programs\KherveBook")
    assert not updater.can_self_update()


def test_installed_copies_self_update(monkeypatch):
    monkeypatch.setattr(updater.os, "name", "nt")
    monkeypatch.setattr(updater, "_is_frozen", lambda: True)
    monkeypatch.setattr(updater, "app_exe",
                        lambda: r"C:\Users\me\Programs\KherveBook\KherveBook.exe")
    monkeypatch.setattr(updater, "_registered_install_dir",
                        lambda: "C:/Users/me/Programs/KherveBook/")
    assert updater.can_self_update()


def test_updater_stays_quiet_when_up_to_date(qapp, monkeypatch):
    """The startup check must not pop anything when there is no new version."""
    from khervebook import __version__

    shown = []
    monkeypatch.setattr(updater.QMessageBox, "information",
                        lambda *a, **k: shown.append(a))
    updater_obj = updater.Updater(None)
    updater_obj._silent = True
    updater_obj._checked({"version": __version__, "url": "", "notes": ""})
    assert not shown


def test_manual_check_reports_being_up_to_date(qapp, monkeypatch):
    from khervebook import __version__

    shown = []
    monkeypatch.setattr(updater.QMessageBox, "information",
                        lambda *a, **k: shown.append(a))
    updater_obj = updater.Updater(None)
    updater_obj._silent = False
    updater_obj._checked({"version": __version__, "url": "", "notes": ""})
    assert shown


def test_skipped_version_is_not_offered_again_on_startup(monkeypatch):
    offered = []
    monkeypatch.setattr(updater, "_skipped_version", lambda: "9.9.9")
    monkeypatch.setattr(updater.Updater, "_offer",
                        lambda self, result: offered.append(result))
    updater_obj = updater.Updater(None)
    updater_obj._silent = True
    updater_obj._checked({"version": "9.9.9", "url": "", "notes": ""})
    assert not offered
    # A manual check still offers it — the user asked.
    updater_obj._silent = False
    updater_obj._checked({"version": "9.9.9", "url": "", "notes": ""})
    assert offered
