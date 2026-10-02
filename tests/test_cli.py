import json
import os
import subprocess
import sys
from pathlib import Path

from flakemap.cli import main


def _write_run(root: Path, run_id: str, sequence: int, failing: bool, commit: str) -> None:
    d = root / run_id
    d.mkdir(parents=True)
    status = '<failure message="boom">boom</failure>' if failing else ""
    (d / "report.xml").write_text(
        f"""<testsuites><testsuite name="s" tests="1" failures="{1 if failing else 0}">
<testcase classname="tests.mod" name="test_thing" time="0.1">{status}</testcase>
</testsuite></testsuites>"""
    )
    (d / "meta.json").write_text(json.dumps({"commit": commit, "sequence": sequence}))


def test_cli_exits_2_on_missing_dir(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    code = main([str(tmp_path / "nope")])
    assert code == 2


def test_cli_exits_2_on_empty_dir(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    empty = tmp_path / "empty"
    empty.mkdir()
    code = main([str(empty)])
    assert code == 2


def test_cli_json_output_is_valid_json(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    root = tmp_path / "runs"
    for i in range(6):
        _write_run(root, f"run-{i}", i, failing=(i % 2 == 0), commit=f"c{i}")
    code = main([str(root), "--json"])
    assert code == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["summary"]["total_runs"] == 6
    assert payload["tests"][0]["test"] == "tests.mod.test_thing"


def test_cli_html_report_is_written(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    root = tmp_path / "runs"
    for i in range(6):
        _write_run(root, f"run-{i}", i, failing=(i % 2 == 0), commit=f"c{i}")
    out_file = tmp_path / "report.html"
    code = main([str(root), "--html", str(out_file)])
    assert code == 0
    html = out_file.read_text()
    assert "<!doctype html>" in html.lower()
    assert "tests.mod.test_thing" in html
    # One file, no script, and a policy that has the browser hold it to that.
    assert "<script" not in html
    assert (
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
        "style-src 'unsafe-inline'; img-src data:; base-uri 'none'; form-action 'none'\">"
    ) in html
    assert html.index("Content-Security-Policy") < html.index("<style")


def test_fail_on_new_flake_exits_1_for_recently_broken_test(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    root = tmp_path / "runs"
    # 10 clean runs, then 8 failing runs: a recent, sharp break.
    for i in range(10):
        _write_run(root, f"run-{i:02d}", i, failing=False, commit=f"c{i}")
    for i in range(10, 18):
        _write_run(root, f"run-{i:02d}", i, failing=True, commit=f"c{i}")
    code = main([str(root), "--fail-on-new-flake", "--new-flake-window", "10"])
    assert code == 1


def test_fail_on_new_flake_is_clean_when_nothing_new(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    root = tmp_path / "runs"
    for i in range(20):
        _write_run(root, f"run-{i:02d}", i, failing=False, commit=f"c{i}")
    code = main([str(root), "--fail-on-new-flake"])
    assert code == 0


def test_markdown_output_contains_table_header(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    root = tmp_path / "runs"
    for i in range(10):
        _write_run(root, f"run-{i}", i, failing=(i % 2 == 0), commit=f"c{i}")
    code = main([str(root), "--markdown"])
    assert code == 0
    out = capsys.readouterr().out
    assert "| Test |" in out


def test_common_prefix_drops_shared_components_only() -> None:
    from flakemap.report.names import common_prefix, short_name

    names = ["tests.test_suite.test_a", "tests.test_suite.test_b", "tests.test_suite.sub.test_c"]
    prefix = common_prefix(names)
    assert prefix == "tests.test_suite."
    assert short_name(names[2], prefix) == "sub.test_c"
    assert common_prefix(["a.x", "b.y"]) == ""
    assert common_prefix(["only.one"]) == ""
    # never swallow a whole name: the last component always stays
    assert common_prefix(["pkg.test_a", "pkg.test_a"]) == "pkg."


# A parametrized test, named the way pytest and Playwright name them: long, and with brackets.
LONG_NAME = (
    "test_checkout_total_matches_the_cart[chromium-desktop-1280x720-logged-in-user-with-coupon]"
)


def _write_history(root: Path) -> None:
    for i in range(30):
        d = root / f"run-{i:02d}"
        d.mkdir(parents=True)
        # Passes for 24 runs, then fails: a change the new-flake gate reports.
        failure = '<failure message="timeout">timeout</failure>' if i >= 24 else ""
        (d / "report.xml").write_text(
            f"""<testsuites><testsuite name="s" tests="2" failures="{1 if failure else 0}">
<testcase classname="tests.e2e.test_checkout" name="{LONG_NAME}" time="0.1">{failure}</testcase>
<testcase classname="tests.e2e.test_checkout" name="test_ok" time="0.1"></testcase>
</testsuite></testsuites>"""
        )
        (d / "meta.json").write_text(json.dumps({"commit": f"c{i}", "sequence": i}))


def _run_piped(root: Path, columns: str | None) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if k != "COLUMNS"}
    if columns:
        env["COLUMNS"] = columns
    return subprocess.run(
        [sys.executable, "-m", "flakemap.cli", str(root), "--fail-on-new-flake"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**env, "PYTHONIOENCODING": "utf-8"},
    )


def test_a_pipe_gets_every_line_whole(tmp_path: Path) -> None:
    """A CI log is where the report is read, and searching it for a test's name has to work."""
    _write_history(tmp_path)
    result = _run_piped(tmp_path, columns=None)
    lines = result.stdout.splitlines()
    assert any(LONG_NAME in line for line in lines), result.stdout
    assert lines[0].endswith("0 insufficient data")
    header = next(line for line in lines if "Final fail (95% CI)" in line)
    assert "Flip rate" in header and "Since" in header
    # stderr is a pipe too: the names in the exit message stay on one line.
    assert any(LONG_NAME in line for line in result.stderr.splitlines()), result.stderr


def test_columns_is_respected_when_set(tmp_path: Path) -> None:
    _write_history(tmp_path)
    result = _run_piped(tmp_path, columns="80")
    lines = result.stdout.splitlines()
    assert all(len(line) <= 80 for line in lines)
    assert not any(LONG_NAME in line for line in lines)  # folded to fit, as in a terminal


def _run_with_code_page(root: Path, *flags: str) -> subprocess.CompletedProcess[bytes]:
    # What Python on Windows gives a redirected stdout: the system's code page.
    env = {k: v for k, v in os.environ.items() if k not in ("COLUMNS", "PYTHONUTF8")}
    env["PYTHONIOENCODING"] = "cp1252"
    return subprocess.run(
        [sys.executable, "-m", "flakemap.cli", str(root), *flags], capture_output=True, env=env
    )


def test_markdown_to_a_file_is_utf8_whatever_the_code_page(tmp_path: Path) -> None:
    # `flakemap runs --markdown > report.md`: the status markers are emoji, which cp1252
    # doesn't have, so this raised UnicodeEncodeError.
    _write_history(tmp_path)
    result = _run_with_code_page(tmp_path, "--markdown")
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    report = result.stdout.decode("utf-8")
    assert "\U0001f534" in report  # the red circle of a broken test
    assert LONG_NAME in report


def test_a_test_name_outside_the_code_page_reaches_the_log(tmp_path: Path) -> None:
    name = "test_\u6ce8\u6587_\u5408\u8a08"
    for i in range(30):
        d = tmp_path / f"run-{i:02d}"
        d.mkdir(parents=True)
        failure = '<failure message="x">x</failure>' if i >= 24 else ""
        (d / "report.xml").write_text(
            f"""<testsuites><testsuite name="s" tests="2">
<testcase classname="tests.t" name="{name}" time="0.1">{failure}</testcase>
<testcase classname="tests.t" name="test_ok" time="0.1"></testcase>
</testsuite></testsuites>""",
            encoding="utf-8",
        )
        (d / "meta.json").write_text(json.dumps({"commit": f"c{i}", "sequence": i}))
    result = _run_with_code_page(tmp_path, "--fail-on-new-flake")
    assert result.returncode == 1, result.stderr.decode("utf-8", "replace")
    assert name in result.stdout.decode("utf-8")
    assert name in result.stderr.decode("utf-8")
