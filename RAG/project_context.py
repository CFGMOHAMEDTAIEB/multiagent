"""Versioned retrieval over the selected project's existing engineering records."""
from copy import deepcopy
import json
from smartx.engineering_workflow import fingerprint
from .embeddings import similarity


def snapshot(state, workflow):
    # Outputs and chat history must not change the identity of their own input.
    draft = state['draft']
    canonical = draft.get('tester_approved', {}).get('contract') or draft.get('tester_json') or {}
    datasets = workflow.get('extraction', {}).get('datasets') or {
        k: canonical.get(k, []) for k in ('requirements', 'parameters', 'samples', 'test_cases')}
    sources = {s['id']: {'id': s['id'], 'name': s['name'], 'hash': s.get('hash', s['id']),
                          'text': s.get('text', '')} for s in workflow.get('sources', [])}
    for s in state.get('documents', []):
        sources.setdefault(s['hash'], {'id': s['hash'], 'hash': s['hash'], 'name': s['name'], 'text': s.get('text', '')})
    records = []
    for collection, rows in datasets.items():
        for index, row in enumerate(rows):
            ref = row.get('source_ref')
            # A canonical import can retain provenance nested in the source field.
            if not ref and len(sources) == 1:
                ref = next(iter(sources))
            location = {k: row[k] for k in ('sheet', 'row', 'line', 'page', 'table') if k in row}
            records.append({'key': fingerprint([collection, index, row]), 'collection': collection,
                'id': str(row.get('id', row.get('name', ''))), 'source_ref': ref,
                'source_version': sources.get(ref, {}).get('hash'), 'location': location or {'status': 'not supplied'},
                'data': deepcopy(row)})
    base = {'client': state['client']['id'], 'project': state['project'],
        'revision': state['client']['revision'], 'settings': state['settings'],
        'project_configuration': state.get('project_detail'), 'aerospace':state.get('aerospace_context'), 'sources': sources, 'records': records,
        'canonical_editor': draft.get('tester_editor'), 'canonical_approval': draft.get('tester_approved'),
        'extraction_review': workflow.get('review'), 'setup': workflow.get('setup')}
    return {'version': fingerprint(base), 'records': records, 'sources': sources,
            'client': base['client'], 'project': base['project']}


def retrieve(context, query, ids=None, limit=20):
    ids = ids or []
    selected = []
    for identifier in ids:
        source_matches = [s['id'] for s in context['sources'].values() if identifier in (s['id'], s['name'])]
        if source_matches:
            if len(source_matches) != 1: raise ValueError('Ambiguous source name; use its versioned ID')
            selected.extend(r for r in context['records'] if r['source_ref'] == source_matches[0])
            continue
        matches = [r for r in context['records'] if r['id'] == identifier or r['key'] == identifier]
        if not matches:
            raise ValueError('Unknown project record: ' + identifier)
        if len(matches) > 1:
            raise ValueError('Ambiguous record ID; select the exact record key: ' + identifier)
        selected.extend(matches)
    if selected:
        return list({r['key']: r for r in selected}.values())
    ranked = sorted(context['records'], key=lambda r: similarity(query, json.dumps(r['data'], ensure_ascii=False)), reverse=True)
    return ranked[:limit]


def traceability(records):
    requirements = [r for r in records if r['collection'] == 'requirements']
    tests = [r for r in records if r['collection'] == 'test_cases']
    known = {r['id'] for r in requirements if r['id']}
    linked, orphan, missing_expected = set(), [], []
    links = []
    for test in tests:
        data = test['data']
        refs = data.get('requirement_ids', data.get('requirement_id', []))
        refs = [refs] if isinstance(refs, str) else refs
        refs = refs if isinstance(refs, list) else []
        valid = [ref for ref in refs if ref in known]
        linked.update(valid)
        links.extend({'requirement_id': ref, 'test_id': test['id'], 'record_key': test['key'],
                      'source_ref': test['source_ref'], 'location': test['location']} for ref in valid)
        if not valid or any(ref not in known for ref in refs): orphan.append(test['id'])
        if not data.get('expected_results', data.get('expected_result', data.get('expected'))): missing_expected.append(test['id'])
    return {'requirements': len(known), 'tests': len(tests), 'links': links,
        'missing_links': sorted(known - linked), 'orphan_tests': orphan, 'missing_expected_results': missing_expected,
        'link_coverage': len(linked) / len(known) if known else None,
        'execution_coverage': None, 'code_coverage': None,
        'limitations': ['Explicit requirement IDs only; no inferred links.',
            'Link coverage does not establish test execution or code coverage.']}
