"""Run the CLI and independently render its Markdown with cmark-gfm.

python capture.py SOURCE_ROOT_OR_INSTALLED_PYTHON INPUTS CMARK OUTPUT [--check]
"""

import hashlib
import json
import os
import re
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path


class Rendered(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text = []
        self.tags = []
        self.code = []
        self.codes = []
        self.code_depth = 0
        self.code_children = 0
        self.links = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        if tag == "a":
            self.links.append(dict(attrs).get("href"))
        if self.code_depth:
            self.code_children += 1
        if tag == "code":
            self.code_depth += 1
            self.code = []

    def handle_endtag(self, tag):
        if tag == "code":
            self.codes.append("".join(self.code))
            self.code_depth -= 1
        if tag in {"p", "td", "tr", "h1", "h2", "blockquote"}:
            self.text.append("\n")

    def handle_data(self, data):
        self.text.append(data)
        if self.code_depth:
            self.code.append(data)


def digest(data):
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def visible(text):
    # Independent display contract: controls become visible escapes; line
    # breaks become spaces. Do not call the implementation's Markdown helper.
    return (
        re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", lambda m: f"\\x{ord(m[0]):02x}", text)
        .replace("\n", " ")
        .replace("\r", " ")
    )


# Resolving a venv's Python symlink selects the base interpreter and loses the
# installed package. Normalize the executable path without following symlinks.
target = Path(os.path.abspath(sys.argv[1]))
inputs, cmark, output = map(lambda arg: Path(arg).resolve(), sys.argv[2:5])
checked = "--check" in sys.argv[5:]
output.mkdir(parents=True, exist_ok=False)
env = {**os.environ, "NO_COLOR": "1", "COLUMNS": "180"}
env.pop("PYTHONPATH", None)
if target.is_dir():
    python = sys.executable
    env["PYTHONPATH"] = str(target / "src")
else:
    python = str(target)
version = subprocess.check_output(
    [
        python,
        "-c",
        "import platform,importlib.metadata as m;print(platform.python_version(),m.version('rich'))",
    ],
    env=env,
    text=True,
).strip()
results = []
for directory in sorted(inputs.iterdir()):
    case = output / directory.name
    case.mkdir()
    base = [python, "-m", "flakemap", str(directory)]
    command_results = []
    for flags, path in [
        (["--markdown"], "report.md"),
        (["--json", "--html", str(case / "standalone.html")], "report.json"),
        ([], "terminal.txt"),
    ]:
        run = subprocess.run(base + flags, env=env, capture_output=True, check=False)
        assert run.returncode == 0, (directory.name, flags, run.stderr.decode())
        (case / path).write_bytes(run.stdout)
        command_results.append({"output": path, "exitCode": run.returncode, **digest(run.stdout)})
    data = json.loads((case / "report.json").read_bytes())
    rendered = subprocess.check_output(
        [
            str(cmark),
            "--unsafe",
            "-e",
            "table",
            "-e",
            "autolink",
            "-e",
            "strikethrough",
            "-e",
            "tagfilter",
            str(case / "report.md"),
        ]
    )
    (case / "rendered.html").write_bytes(rendered)
    parsed = Rendered()
    parsed.feed(rendered.decode())
    expected = []
    for test in data["tests"]:
        if test["classification"] not in {"flaky", "broken"}:
            continue
        expected.append({"field": "test", "value": test["test"]})
        if test["change_point"]:
            expected.append({"field": "change_point_run", "value": test["change_point"]["run_id"]})
        expected.extend(
            {"field": "named_failure", "value": item["name"]} for item in test["named_failures"][:3]
        )
    for group in data["cofailure"]["groups"][:5]:
        expected.extend({"field": "cofailure_test", "value": name} for name in group["tests"][:3])
        failed = set(group["run_states"]["failed"] + group["run_states"]["exhausted"])
        ids = [row["run_id"] for row in data["cofailure"]["runs"] if row["run_id"] in failed][:5]
        ids += group["run_states"]["recovered"][:5]
        expected.extend({"field": "cofailure_run", "value": run_id} for run_id in ids)
    expected.extend({"field": "warning", "value": warning} for warning in data["warnings"])
    text = "".join(parsed.text)
    observations = [{**row, "literal": visible(row["value"]) in text} for row in expected]
    generated_links = [
        href for href in parsed.links if href != "https://github.com/antonsoo/flakemap"
    ]
    if checked:
        assert all(row["literal"] for row in observations), (directory.name, observations)
        assert not generated_links and parsed.tags.count("img") == parsed.code_children == 0, (
            directory.name
        )
    files = {
        name: digest((case / name).read_bytes())
        for name in ["report.md", "report.json", "terminal.txt", "standalone.html", "rendered.html"]
    }
    results.append(
        {
            "name": directory.name,
            "commands": command_results,
            "files": files,
            "fields": observations,
            "images": parsed.tags.count("img"),
            "importedLinks": generated_links,
            "codeChildren": parsed.code_children,
            "codeTexts": parsed.codes,
            "inputFiles": [
                {"path": str(p.relative_to(inputs)), **digest(p.read_bytes())}
                for p in sorted(directory.rglob("*"))
                if p.is_file()
            ],
        }
    )
receipt = {
    "pythonAndRich": version,
    "cmarkVersion": subprocess.check_output([str(cmark), "--version"], text=True).strip(),
    "cmarkBinary": digest(cmark.read_bytes()),
    "checked": checked,
    "workflows": results,
}
(output / "receipt.json").write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + "\n")
print(
    json.dumps(
        {
            "workflows": len(results),
            "literalFields": sum(row["literal"] for case in results for row in case["fields"]),
            "fields": sum(len(case["fields"]) for case in results),
            "images": sum(case["images"] for case in results),
            "importedLinks": sum(len(case["importedLinks"]) for case in results),
        }
    )
)
