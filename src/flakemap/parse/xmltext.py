"""Repairing report text that XML 1.0 rejects only because of a few characters.

Among the C0 control characters XML 1.0 allows only tab, line feed and carriage return; any
other, written raw or as a character reference (``&#27;``), makes the whole document not
well-formed. Test output carries terminal colour codes (ESC ``[31m``) into failure messages,
and some reporters write that ESC into the XML as it is or as ``&#27;``. One such failure
message used to cost the whole file: the parser rejected it, and so did every fragment the
recovery scan tried, because each still held the character.
"""

from __future__ import annotations

import re

_REPLACEMENT = chr(0xFFFD)
# A colour code (or any other CSI sequence), raw or with its ESC as a character reference.
_CSI_RAW = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_CSI_REF = re.compile(r"&#(?:0*27|[xX]0*1[bB]);\[[0-?]*[ -/]*[@-~]")
_BAD_RAW = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_CHAR_REF = re.compile(r"&#(?:[xX]0*([0-9a-fA-F]{1,8})|0*([0-9]{1,10}));")


def _allowed(cp: int) -> bool:
    return (
        cp in (0x9, 0xA, 0xD)
        or 0x20 <= cp <= 0xD7FF
        or 0xE000 <= cp <= 0xFFFD
        or 0x10000 <= cp <= 0x10FFFF
    )


def repair_xml_text(raw: str) -> tuple[str, int, int]:
    """Returns ``(text, colour codes dropped, characters replaced)``.

    Colour codes are presentation, so they are dropped whole. Any other character XML 1.0 does
    not allow becomes U+FFFD: that does change the text, which callers report.
    """
    dropped = 0
    replaced = 0

    def drop(_: re.Match[str]) -> str:
        nonlocal dropped
        dropped += 1
        return ""

    def bad_ref(m: re.Match[str]) -> str:
        nonlocal replaced
        cp = int(m.group(1), 16) if m.group(1) else int(m.group(2))
        if _allowed(cp):
            return m.group(0)
        replaced += 1
        return _REPLACEMENT

    def bad_raw(_: re.Match[str]) -> str:
        nonlocal replaced
        replaced += 1
        return _REPLACEMENT

    text = _CSI_REF.sub(drop, _CSI_RAW.sub(drop, raw))
    text = _BAD_RAW.sub(bad_raw, _CHAR_REF.sub(bad_ref, text))
    return text, dropped, replaced


def replaced_warning(replaced: int) -> str:
    noun = "character" if replaced == 1 else "characters"
    return f"{replaced} {noun} XML does not allow (control characters) replaced with U+FFFD to read the file"
