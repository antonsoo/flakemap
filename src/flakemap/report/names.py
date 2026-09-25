"""Display names for tests: drop the dotted prefix every test shares.

Real suites often put every test under one module path
(`tests.test_suite.test_x`), which makes the distinguishing part of each
name the part that gets truncated first. Reports show the shared prefix
once and each test by its remainder.
"""

from __future__ import annotations


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
