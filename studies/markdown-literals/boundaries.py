"""Check delimiter/pipe/space boundaries using the independent GFM renderer.

Run with the corrected source or installed Python:
python boundaries.py CMARK RECEIPT
"""

import json
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path

from flakemap.report.markdown_out import _literal


class CodeText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.children = 0
        self.codes = []
        self.current = []
        self.active = []

    def handle_starttag(self, tag, attrs):
        if self.depth:
            self.children += 1
        if tag == "code":
            self.depth += 1
            self.current = []
        if tag in {"a", "img", "script"}:
            self.active.append(tag)

    def handle_endtag(self, tag):
        if tag == "code":
            self.codes.append("".join(self.current))
            self.depth -= 1

    def handle_data(self, data):
        if self.depth:
            self.current.append(data)


values = [
    "",
    " ",
    "   ",
    " edge ",
    "  edge  ",
    "`",
    "``",
    "```",
    "`edge`",
    "`first",
    "last`",
    "a `` b ` c",
    "  ` | `  ",
    "|",
    r"\|",
    r"\\|",
    r"\\\|",
    r"a\|b",
    "![img](https://example.invalid/image)",
    "[link](https://example.invalid)",
    "a@example.invalid",
    "www.example.invalid",
    "&amp; &#124; &#96;",
    "</code><img src=x>",
    "*glob* ~~literal~~",
    "日本語_Δ_🙂",
]
rows = []
for in_table in [False, True]:
    for value in values:
        span = _literal(value, in_table=in_table)
        markdown = f"| Value |\n| --- |\n| {span} |\n" if in_table else span + "\n"
        html = subprocess.check_output(
            [sys.argv[1], "--unsafe", "-e", "table", "-e", "autolink", "-e", "strikethrough"],
            input=markdown.encode(),
        ).decode()
        parsed = CodeText()
        parsed.feed(html)
        assert parsed.codes == [value], (value, in_table, html)
        assert not parsed.active and not parsed.children, (value, in_table, html)
        rows.append({"input": value, "inTable": in_table, "markdown": markdown, "html": html})
Path(sys.argv[2]).write_text(
    json.dumps({"cases": len(rows), "results": rows}, ensure_ascii=False, indent=2) + "\n"
)
print(f"{len(rows)} GFM boundary cases preserve exact code text")
