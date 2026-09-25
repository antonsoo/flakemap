import json
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
