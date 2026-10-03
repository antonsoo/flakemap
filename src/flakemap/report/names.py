"""Display names for tests: drop the dotted prefix every test shares.

Real suites often put every test under one module path
(`tests.test_suite.test_x`), which makes the distinguishing part of each
name the part that gets truncated first. Reports show the shared prefix
once and each test by its remainder.
"""

from __future__ import annotations

import re

# XML keeps C0 control characters out of a report, but allows the C1 range, where U+009B is an
# 8-bit CSI that some terminals act on. Test names, run ids and messages are shown, not sent.
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")


def visible(text: str) -> str:
    """``text`` with each control character (bar tab and line breaks) written as ``\\xNN``."""
    return _CONTROL.sub(lambda m: f"\\x{ord(m.group()):02x}", text)


def common_prefix(names: list[str]) -> str:
    """Longest dotted prefix (ending in '.') shared by all names, or ''.

    Only whole components are dropped, and at least one component of every
    name is kept, so `a.b.x` and `a.b.y` share `a.b.`, while a single test,
    or tests with nothing in common, yield ''.
    """
    if len(names) < 2:
        return ""
    split = [n.split(".") for n in names]
    shared: list[str] = []
    for parts in zip(*(s[:-1] for s in split), strict=False):
        if all(p == parts[0] for p in parts):
            shared.append(parts[0])
        else:
            break
    return ".".join(shared) + "." if shared else ""


def short_name(full_name: str, prefix: str) -> str:
    return full_name[len(prefix) :] if prefix and full_name.startswith(prefix) else full_name
