"""Human-readable projection of the canonical assessment (no extra verdict)."""
import json


def render_markdown(report):
    def compact(value):
        return json.dumps(value, ensure_ascii=False, sort_keys=True).replace('|', '\\|').replace('\n', ' ')
    counts = report['summary']
    lines = ['# Compose UX evidence review', '',
             f"Status: **{report['overall_status']}**. Scope: `{report['verdict_scope']}` / `{report['validation_scope']}`.", '',
             f"Checks: {counts['pass']} pass, {counts['fail']} fail, {counts['inconclusive']} inconclusive, {counts['not_applicable']} not applicable.",
             'Coverage counts evaluated declared checks; it is not a UX quality percentage.', '',
             '| Requirement | Status | Expected | Observed | Reason |', '|---|---|---|---|---|']
    for item in report['findings']:
        lines.append('| ' + ' | '.join([compact(item['id']), item['status'], compact(item.get('expected')), compact(item.get('observed')), compact(item['reason'])]) + ' |')
    lines += ['', '## Evidence', '']
    for item in report['findings']:
        lines.append(f"- `{item['id']}`: " + compact({'capture_id': item.get('capture_id'), 'source': item.get('source'), 'runtime_tag': item.get('runtime_tag'), 'references': item['evidence']}))
    lines += ['', '## Design preparation issues', '', '```json', json.dumps(report.get('design_issues', []), ensure_ascii=False, indent=2), '```']
    lines += ['', '## Provenance', '', '```json', json.dumps(report['provenance'], ensure_ascii=False, indent=2), '```', '', '## Limits and next checks', '']
    lines += ['- ' + value for value in report['limitations']] or ['- No additional machine-evidence limitations recorded.']
    lines += ['- Inspect the original design, actual and diff images; review task clarity, wording, accessibility, failure states and navigation separately. This deterministic report covers only its declared checks.', '']
    return '\n'.join(lines)
