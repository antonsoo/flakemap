"""Bounded, script-free inspection of exact shared outcomes and their source records."""

from __future__ import annotations

import base64
import json
from html import escape

from flakemap.report.json_out import cofailure_to_dict
from flakemap.report.names import common_prefix, short_name, visible
from flakemap.stats.analyze import AnalysisResult
from flakemap.stats.cofailure import FailureCohort

MAX_GROUPS = 20
MAX_MEMBERS = 20
MAX_EVIDENCE = 40
MAX_RUN_LABELS = 20


def _text(value: str, limit: int = 240) -> str:
    value = visible(value)
    return escape(value if len(value) <= limit else value[:limit] + "... [full text in JSON]")


def _group(group: FailureCohort, test_anchors: dict[str, str]) -> str:
    members = []
    for name in group.tests[:MAX_MEMBERS]:
        anchor = test_anchors.get(name)
        label = f"<code>{_text(name)}</code>"
        members.append(
            f'<li><a href="#{anchor}">{label}</a></li>' if anchor else f"<li>{label}</li>"
        )
    states = []
    labels = {
        "pass": "Pass without retry",
        "failed": "Final fail or error",
        "recovered": "Passed on retry",
        "exhausted": "Retries exhausted",
        "skip": "Skipped",
        "absent": "Not reported",
    }
    for state, ids in group.states.items():
        if not ids:
            continue
        run_labels = ", ".join(
            f"<code>{_text(run_id, 100)}</code>" for run_id in ids[:MAX_RUN_LABELS]
        )
        if len(ids) > MAX_RUN_LABELS:
            run_labels += f"; {len(ids) - MAX_RUN_LABELS} more in JSON"
        states.append(f"<dt>{labels[state]} ({len(ids)})</dt><dd>{run_labels}</dd>")
    rows = []
    prefix = common_prefix(list(group.tests))
    for observation in group.evidence[:MAX_EVIDENCE]:
        md = observation.run.metadata
        record = observation.result
        context = (
            " / ".join(part for part in (md.runner, md.os) if part) or "Environment not recorded"
        )
        commit = f"<br>commit <code>{_text(md.commit, 64)}</code>" if md.commit else ""
        source = (
            f"{record.source.report} :: testcase {record.source.testcase}"
            if record.source
            else "Source location not supplied"
        )
        outcome = record.status.value
        messages = []
        if record.retry:
            outcome += f"; {record.retry.outcome}; {record.retry.attempts} attempts"
            messages = [
                f"{failure.tag}: {failure.message or '(no message)'}"
                for failure in record.retry.failures[:3]
            ]
            if len(record.retry.failures) > 3:
                messages.append(f"{len(record.retry.failures) - 3} more failed attempts in JSON")
        elif record.message:
            messages = [record.message]
        rows.append(
            f'<tr><th scope="row"><code>{_text(md.run_id, 100)}</code>'
            f'<br><span class="cohort-context">{_text(context, 180)}{commit}</span></th>'
            f"<td><code>{_text(short_name(record.full_name, prefix))}</code></td>"
            f"<td>{_text(outcome)}</td><td><code>{_text(source)}</code>"
            + "".join(f"<p>{_text(message, 360)}</p>" for message in messages)
            + "</td></tr>"
        )
    return (
        f'<details class="cohort" id="{group.id}"><summary>'
        f"<strong>{len(group.tests)} tests</strong> share {group.failed_runs} final-failure runs"
        f' and {group.recovered_runs} recovered runs</summary><div class="cohort-detail">'
        '<h3>Matching run history</h3><dl class="cohort-states">' + "".join(states) + "</dl>"
        f'<h3>Members ({len(group.tests)})</h3><ul class="cohort-members">'
        + "".join(members)
        + "</ul>"
        + (
            f"<p>{len(group.tests) - MAX_MEMBERS} more members in the JSON download.</p>"
            if len(group.tests) > MAX_MEMBERS
            else ""
        )
        + f'<p class="cohort-limit">Showing {min(len(group.evidence), MAX_EVIDENCE)} of '
        f"{len(group.evidence)} affected test-runs. Source positions are 1-based result ordinals. "
        "Long text and retry lists are previewed; the JSON download retains every record.</p>"
        '<p class="cohort-scroll-hint">Scroll the evidence table horizontally to inspect every column.</p>'
        f'<div class="cohort-scroll" role="region" tabindex="0" aria-label="Evidence for {group.id}">'
        "<table><caption>Original failures and recovered retries</caption><thead><tr>"
        '<th scope="col">Run / environment</th><th scope="col">Test</th>'
        '<th scope="col">Reported outcome</th><th scope="col">Source and message</th>'
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></div></div></details>"
    )


def render_cofailure(result: AnalysisResult, test_anchors: dict[str, str]) -> str:
    analysis = result.cofailure
    if not analysis.groups:
        return ""
    payload = {
        "schema_version": 1,
        "input_complete": not result.warnings,
        "warnings": result.warnings,
        "cofailure": cofailure_to_dict(analysis),
    }
    encoded = base64.b64encode(json.dumps(payload, allow_nan=False).encode()).decode("ascii")
    grouped_tests = sum(len(group.tests) for group in analysis.groups)
    excluded = (
        f"<p>{len(analysis.excluded_tests)} tests have ambiguous outcomes and are excluded "
        "from grouping. See their individual evidence below.</p>"
        if analysis.excluded_tests
        else ""
    )
    return (
        '<section class="cofailure" aria-labelledby="cofailure-heading">'
        '<h2 id="cofailure-heading">Tests that fail together</h2>'
        f"<p>{grouped_tests} tests in {len(analysis.groups)} exact outcome "
        f"{'cohort' if len(analysis.groups) == 1 else 'cohorts'}. "
        "Each group has the same normalized outcomes, retry states, skips and missing runs. "
        "A shared history is a lead to investigate, not proof of a common cause.</p>"
        + excluded
        + f'<a class="cofailure-download" download="flakemap-cofailure.json" '
        f'href="data:application/json;base64,{encoded}">Download all shared-outcome evidence</a>'
        + f'<p class="cohort-limit">Showing {min(len(analysis.groups), MAX_GROUPS)} of '
        f"{len(analysis.groups)} cohorts, ordered by affected test-runs. "
        "Final failures and passed-on-retry results remain separate.</p>"
        + "".join(_group(group, test_anchors) for group in analysis.groups[:MAX_GROUPS])
        + "</section>"
    )


COFAILURE_CSS = """
.cofailure { padding: 1.75rem 1.5rem 0; font-size: .86rem; overflow-wrap: anywhere; }
.cofailure h2 { font-family: var(--font-display); text-transform: uppercase; letter-spacing: .05em;
  font-size: 1.05rem; border-bottom: 2px solid var(--ink); padding-bottom: .4rem; }
.cofailure a { color: var(--accent); text-underline-offset: .15em; }
.cofailure a:focus-visible, .cohort summary:focus-visible, .cohort-scroll:focus-visible {
  outline: 2px solid var(--accent); outline-offset: 3px; }
.cohort { margin: .6rem 0; border: 1px solid var(--grid-line); background: var(--paper-raised); }
.cohort summary { padding: .8rem; cursor: pointer; line-height: 1.6; }
.cohort summary strong { font-family: var(--font-mono); margin-right: .25em; }
.cohort-detail { padding: 0 1rem 1rem; }
.cohort-detail h3 { font-size: .85rem; margin: 1rem 0 .5rem; }
.cohort-states { display: grid; grid-template-columns: 12rem minmax(0, 1fr); gap: .4rem 1rem; }
.cohort-states dt { color: var(--ink-soft); }
.cohort-states dd { margin: 0; }
.cohort-members { padding-left: 1.2rem; line-height: 1.7; }
.cohort-limit, .cohort-context, .cohort-scroll-hint { color: var(--ink-soft); font-size: .8rem; }
.cohort-scroll { overflow-x: auto; }
.cohort table { width: 100%; min-width: 800px; border-collapse: collapse; table-layout: fixed; font-size: .78rem; }
.cohort caption { text-align: left; padding: .6rem 0; font-weight: 600; }
.cohort th, .cohort td { text-align: left; vertical-align: top; padding: .7rem; border-bottom: 1px solid var(--grid-line); }
.cohort th:nth-child(1) { width: 23%; }
.cohort th:nth-child(2) { width: 23%; }
.cohort th:nth-child(3) { width: 17%; }
.cohort tbody th { font-weight: normal; }
.cohort td p { margin: .45rem 0 0; }
.row summary:target { outline: 2px solid var(--accent); outline-offset: -2px; }
@media (min-width: 950px) { .cohort-scroll-hint { display: none; } }
@media (max-width: 600px) { .cohort-states { grid-template-columns: 1fr; gap: .3rem; }
  .cohort-states dd { margin-bottom: .5rem; } .cohort-detail { padding: 0 .65rem .65rem; } }
"""
