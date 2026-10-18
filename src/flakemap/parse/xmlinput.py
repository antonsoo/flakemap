"""Bounded report reads and XML text decoding shared by JUnit, NUnit and TRX."""

from __future__ import annotations

import codecs
import re
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from typing import cast
from xml.etree import ElementTree as ET

from flakemap.models import Status, TestCaseResult

MAX_REPORT_BYTES = 64 * 1024 * 1024
MAX_XML_DEPTH = 256
MAX_XML_ELEMENTS = 250_000
_DECLARATION = re.compile(rb"^\s*<\?xml\s[^>]*?encoding\s*=\s*['\"]([^'\"]+)['\"]", re.I)
_DTD = re.compile(r"<!\s*(?:DOCTYPE|ENTITY)\b", re.I)
_SPECIAL_MARKUP = re.compile(r"<[!?]")


def xml_events(raw: str) -> Iterator[tuple[str, ET.Element]]:
    parser: ET.XMLPullParser[ET.Element] = ET.XMLPullParser(events=("start", "end"))
    for offset in range(0, len(raw), 16_384):
        parser.feed(raw[offset : offset + 16_384])
        yield from cast(Iterator[tuple[str, ET.Element]], parser.read_events())
    try:
        parser.close()
    except ET.ParseError:
        # Expat may defer a long token until EOF. Even a failed close can have
        # queued completed testcase events, which belong to the recovered prefix.
        yield from cast(Iterator[tuple[str, ET.Element]], parser.read_events())
        raise
    yield from cast(Iterator[tuple[str, ET.Element]], parser.read_events())


def parse_xml_root(raw: str) -> ET.Element:
    """Parse a complete document within the shared XML depth/element limits."""
    depth = 0
    elements = 0
    root = None
    for event, element in xml_events(raw):
        if event == "start":
            elements += 1
            if elements > MAX_XML_ELEMENTS:
                raise ET.ParseError(f"XML exceeds the {MAX_XML_ELEMENTS} element limit")
            depth += 1
            if depth > MAX_XML_DEPTH:
                raise ET.ParseError(f"XML nesting exceeds the {MAX_XML_DEPTH} level limit")
            if root is None:
                root = element
        else:
            depth -= 1
    if root is None:
        raise ET.ParseError("no document element")
    return root


def has_xml_root(raw: str, name: str) -> bool:
    """Inspect the first tag, ignoring declarations/comments, without parsing a body."""
    pos = 0
    while pos < len(raw):
        if raw[pos].isspace() or raw[pos] == "\ufeff":
            pos += 1
            continue
        terminator = (
            "-->" if raw.startswith("<!--", pos) else "?>" if raw.startswith("<?", pos) else None
        )
        if terminator is None:
            return (
                re.compile(r"<(?:[\w.-]+:)?" + re.escape(name) + r"[\s>/]").match(raw, pos)
                is not None
            )
        end = raw.find(terminator, pos + 2)
        if end == -1:
            return False
        pos = end + len(terminator)
    return False


def contains_dtd(raw: str) -> bool:
    """Inspect markup, not a quoted DTD example in a comment or CDATA."""
    pos = 0
    # Comments, CDATA, processing instructions and declarations all open with "<!" or
    # "<?"; an ordinary tag is none of them, and a report is nearly all ordinary tags.
    while (special := _SPECIAL_MARKUP.search(raw, pos)) is not None:
        pos = special.start()
        terminator = None
        if raw.startswith("<!--", pos):
            terminator = "-->"
        elif raw.startswith("<![CDATA[", pos):
            terminator = "]]>"
        elif raw.startswith("<?", pos):
            terminator = "?>"
        elif _DTD.match(raw, pos):
            return True
        if terminator:
            end = raw.find(terminator, pos + 2)
            if end == -1:
                return False  # unfinished text stays in that lexical context
            pos = end + len(terminator)
        else:
            pos += 1
    return False


def decode_xml(raw: bytes) -> tuple[str | None, list[str]]:
    """Honor Unicode signatures and text encodings declared in the XML header.

    Unsupported encodings are errors, never guessed. Invalid bytes in a known
    encoding remain replacement characters with an explicit coverage warning.
    """
    if raw.startswith((codecs.BOM_UTF32_LE, codecs.BOM_UTF32_BE)):
        encoding = "utf-32"
    elif raw.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        encoding = "utf-16"
    elif raw.startswith(b"\x00\x00\x00<"):
        encoding = "utf-32-be"
    elif raw.startswith(b"<\x00\x00\x00"):
        encoding = "utf-32-le"
    elif raw.startswith(b"\x00<"):
        encoding = "utf-16-be"
    elif raw.startswith(b"<\x00"):
        encoding = "utf-16-le"
    elif raw.startswith(codecs.BOM_UTF8):
        encoding = "utf-8-sig"
    else:
        declaration = _DECLARATION.match(raw[:4096])
        try:
            encoding = declaration[1].decode("ascii") if declaration else "utf-8"
        except UnicodeDecodeError:
            return None, ["XML encoding declaration is not ASCII; report omitted"]
    try:
        # bytes.decode rejects non-text transformations such as base64_codec.
        codec = codecs.lookup(encoding)
        if codec.name in ("unicode-escape", "raw-unicode-escape"):
            return None, ["unsupported XML text encoding; report omitted"]
        return raw.decode(encoding), []
    except LookupError:
        return None, ["unsupported XML text encoding; report omitted"]
    except UnicodeError:
        try:
            text = raw.decode(encoding, errors="replace")
        except (LookupError, UnicodeError):
            return None, ["could not decode XML text; report omitted"]
        label = "UTF-8" if encoding in ("utf-8", "utf-8-sig") else encoding
        return text, [
            f"invalid {label} bytes were replaced; verify test identifiers before using this report"
        ]


def read_xml_file(path: Path) -> tuple[str | None, list[str]]:
    try:
        with path.open("rb") as handle:
            raw = handle.read(MAX_REPORT_BYTES + 1)
    except OSError as exc:
        return None, [f"could not read file: {exc}"]
    if len(raw) > MAX_REPORT_BYTES:
        return None, [f"report exceeds the {MAX_REPORT_BYTES} byte limit; report omitted"]
    return decode_xml(raw)


def exclude_lossy_identifiers(
    cases: list[TestCaseResult], warnings: list[str]
) -> list[TestCaseResult]:
    """Different invalid byte sequences must not collapse into one test identity."""
    if not any(
        "bytes were replaced" in warning or "replaced with U+FFFD" in warning
        for warning in warnings
    ):
        return cases
    result = []
    for case in cases:
        if "\ufffd" in case.name or "\ufffd" in case.classname:
            issue = "undecodable or repaired characters in test identity; cannot compare this test across runs"
            if case.issue == issue:
                result.append(case)
                continue
            case = replace(case, status=Status.UNKNOWN, issue=issue)
            warnings.append(f"{case.full_name}: {issue}; excluded from rates")
        result.append(case)
    return result


def without_declaration(raw: str) -> str:
    # Parsing decoded text must not ask Expat to re-interpret its encoding.
    return re.sub(r"^\ufeff?\s*<\?xml[^>]*\?>", "", raw, count=1)
