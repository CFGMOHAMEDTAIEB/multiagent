"""Focused engineering pages, using the existing tester and universal APIs."""
import hashlib
import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from smartx.clients import ClientStore, bind_client
from smartx.testing import canonicalize, validate_contract, verify, generate_tests
from smartx.universal import UniversalStore, validate_settings
from FRONTED.ui.client_workspace import goto

PAGES = ['Dashboard', 'Projects', 'Smart Import', 'Smart Check', 'Test Generation', 'AI Agent Studio', 'Client configuration', 'Rules Manager', 'Reports']
STEPS = ['Upload', 'AI Understanding', 'Review & Edit', 'Proceed']


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def save_draft(directory, state):
    payload = {key: state[key] for key in ('tester_json', 'tester_editor', 'tester_approved', 'tester_output', 'verification_output', 'generation_output', 'import_step', 'generation_review', 'finding_reviews') if key in state}
    ClientStore._atomic(Path(directory) / 'ui-draft.json', json.dumps(payload, ensure_ascii=False, indent=2).encode())


def restore_draft(directory, state):
    scope = str(directory)
    if state.get('draft_scope') == scope:
        return
    for key in ('tester_json', 'tester_editor', 'tester_approved', 'tester_output', 'verification_output', 'generation_output', 'import_step', 'generation_review', 'finding_reviews', 'focused_finding'):
        state.pop(key, None)
    path = Path(directory) / 'ui-draft.json'
    if path.exists():
        payload = json.loads(path.read_text('utf-8'))
        for key in ('tester_json', 'tester_editor', 'tester_approved', 'tester_output', 'verification_output', 'generation_output', 'import_step', 'generation_review', 'finding_reviews'):
            if key in payload:
                state[key] = payload[key]
    state['draft_scope'] = scope


def approved_contract(state):
    approved = state.get('tester_approved')
    if approved and approved.get('hash') == digest(state.get('tester_editor', '')):
        contract = approved['contract']
        scope = state.get('workspace_scope')
        client = contract.get('client', {})
        if scope and (client.get('id') != scope[0] or client.get('revision') != scope[1]):
            return None
        return contract
    return None


def table(st, rows):
    if rows:
        st.dataframe([{k: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v for k, v in row.items()} for row in rows], hide_index=True, width='stretch')
    else:
        st.info('No records available for this project yet.')


def navigate(st, title, page, key=None):
    st.button(title, on_click=goto, args=(st, page), key=key, width='stretch')


def render_dashboard(st, store, client, project):
    st.header('Dashboard', anchor=False)
    st.caption(f"Welcome back. Here is your overview for {client['name']} / {project}.")
    st.markdown('<div class="sx-hero"><div class="sx-eyebrow">ENGINEERING WORKSPACE</div><h2>Start a new workflow</h2><p>Turn engineering documents into reviewed, traceable test evidence.</p></div>', unsafe_allow_html=True)
    for col, title, page in zip(st.columns(3), ['＋ Import File', 'Run Smart Check', 'Generate Tests'], ['Smart Import', 'Smart Check', 'Test Generation']):
        with col:
            navigate(st, title, page)
    docs = store.documents(client['id'], project)
    contract = st.session_state.get('tester_json', {})
    output = st.session_state.get('tester_output', {})
    metrics = [('Documents', len(docs)), ('Requirements', len(contract.get('requirements', []))), ('Test cases', len(output.get('cases', []))), ('Verification findings', len(output.get('findings', []))), ('Traceability', '—'), ('Active project', project)]
    for col, (label, value) in zip(st.columns(6), metrics):
        col.metric(label, value)
    st.caption('Document counts are persisted; requirements and results describe the recovered current draft. Execution coverage has not been measured.')
    left, right = st.columns([3, 1])
    with left, st.container(border=True):
        st.subheader('Recent activities')
        table(st, [{'File': d['name'], 'Type': 'Client guidance' if d.get('guidance') else 'Document', 'Status': 'Saved'} for d in docs[-8:]])
    with right, st.container(border=True):
        st.subheader('Agent system')
        connection = st.session_state.get('ai_connection_status', {})
        st.write('Provider: ' + connection.get('provider', 'Not checked'))
        st.caption('Connection verified' if connection.get('ok') else 'Availability not verified')
        navigate(st, 'Open Agent Studio', 'AI Agent Studio')
    navigate(st, 'Configure this client', 'Client configuration')


def render_import(st, sources, router, context, directory):
    st.header('Smart Import', anchor=False)
    st.caption('Upload, understand, review, and save your engineering evidence.')
    pending = st.session_state.pop('pending_canonical_edit', None)
    if pending is not None:
        st.session_state.tester_editor = pending
        st.session_state.pop('tester_approved', None)
        st.session_state.pop('tester_output', None)
        st.session_state.pop('generation_review', None)
        save_draft(directory, st.session_state)
    step = st.session_state.get('import_step', 0)
    selected = st.radio('Import stage', range(4), index=step, format_func=lambda i: f'{i+1}  {STEPS[i]}', horizontal=True)
    if selected != step:
        st.session_state.import_step = selected
        save_draft(directory, st.session_state)
        step = selected
    for col, i in zip(st.columns(4), range(4)):
        col.markdown(f'<div class="sx-step {"active" if i == step else ""}">{i+1:02d} &nbsp; {STEPS[i]}</div>', unsafe_allow_html=True)
    if step == 0:
        left, right = st.columns([3, 1])
        with left, st.container(border=True):
            st.markdown('<div class="sx-upload-label">Drop your files here</div><div class="sx-upload-help">PDF · DOCX · XLSX · XLSM · XLS · CSV · PTU · XML · JSON · C/C++ · TXT · MD</div>', unsafe_allow_html=True)
            uploaded = st.file_uploader('Choose files', accept_multiple_files=True, type=['txt','md','json','xml','csv','xlsx','xls','xlsm','docx','pdf','c','h','cpp','cc','hpp','ptu'], key='wizard-files-' + str(directory), label_visibility='collapsed', help='Supported formats: PDF, DOCX, XLSX, XLSM, XLS, CSV, PTU, XML, JSON, C/C++, TXT and MD.')
            pasted = st.text_area('Or paste source text', key='wizard-text-' + str(directory), height=100)
            local_sources = [(f.name, f.getvalue()) for f in uploaded or []]
            if pasted.strip():
                try:
                    json.loads(pasted)
                    pasted_name = 'pasted_text.json'
                except ValueError:
                    pasted_name = 'pasted_text.txt'
                local_sources.append((pasted_name, pasted.encode()))
            local_sources = local_sources or sources
            table(st, [{'File': n, 'Size (KB)': round(len(d)/1024, 2), 'Format': Path(n).suffix.lstrip('.').upper()} for n,d in local_sources])
        with right, st.container(border=True):
            st.subheader('Import options')
            st.write('Client: ' + context['name'])
            st.caption('Client field mappings and naming conventions apply automatically.')
            st.caption('10 MB per file. Scanned PDFs require OCR before upload. Readers depend on installed adapters; extraction errors are shown explicitly.')
            with st.expander('Advanced options'):
                st.json({'csv_delimiter': context.get('csv_delimiter', ','), 'provider': router.name})
        if st.button('Continue →', type='primary', disabled=not local_sources):
            try:
                with st.spinner('Parsing source files…'):
                    contract = canonicalize(local_sources, router, context)
                st.session_state.tester_json = contract
                st.session_state.tester_editor = json.dumps(contract, indent=2, ensure_ascii=False, default=str)
                for key in ('tester_approved', 'tester_output', 'generation_review'):
                    st.session_state.pop(key, None)
                st.session_state.import_step = 1
                save_draft(directory, st.session_state)
                st.rerun()
            except Exception as exc:
                st.error(f'Import failed: {exc}')
        return
    contract = st.session_state.get('tester_json')
    if not contract:
        st.info('Upload and convert a source file to continue.')
        return
    if step == 1:
        tabs = st.tabs(['Source Preview', 'Structure', 'Detected Entities', 'AI Analysis', 'Processing Logs'])
        with tabs[0]:
            for source in contract.get('sources', []):
                with st.expander(source['name'], expanded=True):
                    st.text(source.get('content', ''))
        with tabs[1]:
            st.json({k: len(v) for k,v in contract.items() if isinstance(v,list)})
        with tabs[2]:
            table(st, contract.get('requirements', []))
            table(st, contract.get('parameters', []))
        with tabs[3]:
            st.info('Extraction is a proposal. Review source references and constraints before approval. A configured provider does not establish successful live generation.')
            for warning in contract.get('warnings', []):
                st.warning(warning)
        with tabs[4]:
            st.json(contract.get('audit', []))
        if st.button('Review JSON →', type='primary'):
            st.session_state.import_step = 2
            save_draft(directory, st.session_state)
            st.rerun()
    elif step == 2:
        tabs = st.tabs(['Canonical JSON', 'Table View', 'Schema', 'Field Mapping', 'Validation Issues'])
        with tabs[0]:
            left, right = st.columns([3, 2])
            with left:
                st.text_area('Canonical JSON', key='tester_editor', height=430, on_change=save_draft, args=(directory, st.session_state))
            with right, st.container(border=True):
                st.subheader('Field editor')
                try:
                    field_contract = json.loads(st.session_state.tester_editor)
                    collection = st.selectbox('Collection', ['parameters', 'requirements', 'samples'])
                    entries = field_contract.get(collection, [])
                    if entries:
                        position = st.selectbox('Record', range(len(entries)), format_func=lambda i: str(entries[i].get('id', entries[i].get('name', entries[i].get('parameter', i+1)))))
                        with st.form('canonical-field-editor'):
                            record_json = st.text_area('Record fields JSON', json.dumps(entries[position], indent=2), height=230, key='record-'+collection+'-'+str(position)+'-'+digest(json.dumps(entries[position],sort_keys=True)))
                            if st.form_submit_button('Apply record changes'):
                                try:
                                    replacement = json.loads(record_json)
                                    if not isinstance(replacement, dict):
                                        raise ValueError('A record must be an object')
                                    field_contract[collection][position] = replacement
                                    validate_contract(field_contract)
                                    st.session_state.pending_canonical_edit = json.dumps(field_contract, indent=2, ensure_ascii=False)
                                    st.rerun()
                                except (ValueError, TypeError) as exc:
                                    st.error(str(exc))
                        st.caption('Source: '+str(entries[position].get('source', 'No source reference')))
                    else:
                        st.caption('No records in this collection. Add them in the canonical JSON editor.')
                except (ValueError, TypeError, AttributeError):
                    st.caption('Correct the canonical JSON to enable field editing.')
        try:
            edited = json.loads(st.session_state.tester_editor)
            validate_contract(edited)
            issues = None
        except Exception as exc:
            edited, issues = {}, str(exc)
        with tabs[1]:
            table(st, edited.get('parameters', []))
            table(st, edited.get('requirements', []))
        with tabs[2]:
            st.caption('Existing tester-1 contract validator checks requirements, parameters, samples, types and constraints. No alternative schema is introduced.')
            st.code('sources[] · requirements[] · parameters[] · samples[] · warnings[] · audit[]')
        with tabs[3]:
            st.caption('Client mappings apply during import. Changing mappings requires importing again.')
            navigate(st, 'Edit client mappings', 'Client configuration')
        with tabs[4]:
            st.error(issues) if issues else st.success('Contract structure is valid. Human review is still required.')
        reviewer = st.text_input('Reviewer name', key='tester_reviewer')
        if st.button('Validate & Continue →', type='primary', disabled=bool(issues)):
            if not reviewer.strip():
                st.error('Enter a reviewer name.')
            else:
                reviewed = bind_client(validate_contract(edited), context)
                reviewed.setdefault('audit', []).append({'agent':'human_review','reviewer':reviewer.strip(),'decision':'approve','at':datetime.now(timezone.utc).isoformat()})
                st.session_state.tester_approved = {'hash':digest(st.session_state.tester_editor),'contract':reviewed}
                st.session_state.pop('tester_output', None)
                st.session_state.import_step = 3
                save_draft(directory, st.session_state)
                st.rerun()
    else:
        if not approved_contract(st.session_state):
            st.warning('Review and approve the current JSON before proceeding.')
            return
        st.success('Canonical contract reviewed and saved to this project draft.')
        for col, key in zip(st.columns(3), ['sources','requirements','parameters']):
            col.metric(key.title(),len(contract.get(key,[])))
        action_columns = st.columns(3)
        with action_columns[0]:
            navigate(st, 'Run Smart Check', 'Smart Check')
        with action_columns[1]:
            navigate(st, 'Generate Tests', 'Test Generation')
        with action_columns[2]:
            if st.button('Save to Project', width='stretch'):
                try:
                    save_draft(directory, st.session_state)
                    st.success('Reviewed draft saved to this project.')
                except OSError as exc:
                    st.error(f'Unable to save draft: {exc}')


def render_check(st, directory):
    st.header('Smart Check', anchor=False)
    contract = approved_contract(st.session_state)
    if not contract:
        st.info('Import and approve a canonical contract before verification.')
        navigate(st,'Open Smart Import','Smart Import')
        return
    st.caption('Document: ' + ', '.join(s['name'] for s in contract.get('sources',[])) + ' · Approved contract · Deterministic constraint checks')
    if st.button('Run Check', type='primary'):
        try:
            output = verify(contract)
            output['input_hash'] = digest(st.session_state.tester_editor)
            st.session_state.tester_output = output
            st.session_state.verification_output = output
            st.session_state.pop('focused_finding', None)
            save_draft(directory, st.session_state)
        except Exception as exc:
            st.error(str(exc))
    output = st.session_state.get('verification_output', st.session_state.get('tester_output', {}))
    if output.get('agent') != 'verification' or output.get('input_hash') != digest(st.session_state.tester_editor):
        st.info('Run a check to see findings. No verification results are available for the current contract.')
        return
    findings = output.get('findings',[])
    tabs = st.tabs(['Findings','Summary','Coverage','Rule Details','Logs'])
    with tabs[0]:
        left,right = st.columns([3,1])
        query = left.text_input('Search findings',placeholder='Parameter, rule, or result')
        status = right.selectbox('Status',['All','FAIL','PASS','INSUFFICIENT_INFORMATION'])
        visible = [(i,f) for i,f in enumerate(findings) if (status=='All' or f['status']==status) and query.casefold() in json.dumps(f).casefold()]
        table(st,[{'Finding':f'F-{i+1:03d}','Status':f['status'],'Parameter':f.get('parameter'),'Actual':f.get('value'),'Checks':f.get('checks',[])} for i,f in visible])
        if visible:
            index = st.selectbox('Finding details',[i for i,_ in visible],format_func=lambda i:f'F-{i+1:03d} · {findings[i].get("parameter", "Unknown")}')
            finding = findings[index]
            with st.container(border=True):
                st.subheader(f'F-{index+1:03d} · {finding["status"]}')
                detail = st.tabs(['Overview','Source Evidence','Rule Details','Suggested Fix','History'])
                with detail[0]: st.json(finding)
                with detail[1]:
                    st.json({k:v for k,v in finding.items() if k in ('source','row','line','parameter','value')})
                    for source in contract.get('sources',[]):
                        if source.get('name') == finding.get('source'):
                            st.text(source.get('content',''))
                with detail[2]: st.json(finding.get('checks',[]))
                with detail[3]:
                    st.caption('No automatic correction is supplied by this verifier. Review the evidence, edit the canonical draft in Smart Import, then approve and re-check. Original files remain intact.')
                    navigate(st,'Review canonical JSON','Smart Import',key='finding-edit')
                with detail[4]:
                    table(st,st.session_state.get('finding_reviews',[]))
                reviewer = st.text_input('Finding reviewer')
                decision = st.selectbox('Review status',['Reviewed','Needs correction','Rejected'])
                if st.button('Save finding review',disabled=not reviewer.strip()):
                    st.session_state.setdefault('finding_reviews',[]).append({'finding':f'F-{index+1:03d}','input_hash':output['input_hash'],'reviewer':reviewer,'decision':decision,'at':datetime.now(timezone.utc).isoformat()})
                    save_draft(directory,st.session_state)
                    st.success('Review recorded.')
    with tabs[1]:
        for col,status in zip(st.columns(3),['PASS','FAIL','INSUFFICIENT_INFORMATION']):
            col.metric(status.replace('_',' '),sum(f['status']==status for f in findings))
    with tabs[2]:
        table(st,[{'Requirement':p.get('requirement_id'),'Parameter':p['name'],'Source':p.get('source')} for p in contract.get('parameters',[])])
        st.caption('Declared requirement-to-parameter links only. System execution coverage is not measured.')
    with tabs[3]:
        table(st,output.get('client_checks',[]))
        st.caption('This checker evaluates approved parameter constraints and client conventions. Configure documented standard packs in Rules Manager; run those packs through the existing Agent Studio workflow.')
    with tabs[4]:
        st.json(contract.get('audit',[]))
        st.write(output.get('note',''))


def render_generation(st,directory):
    st.header('Test Generation',anchor=False)
    st.caption('Generate draft contract tests, review their traceability, and export for integration with your system.')
    contract=approved_contract(st.session_state)
    if not contract:
        st.info('Approve an imported contract first.')
        navigate(st,'Open Smart Import','Smart Import')
        return
    tabs=st.tabs(['Requirements','Generation Configuration','Generated Tests','Validation','Export'])
    with tabs[0]:
        requirements=contract.get('requirements',[])
        ids=[r['id'] for r in requirements]
        selected=st.multiselect('Select requirements',ids,default=ids)
        table(st,[r for r in requirements if r['id'] in selected])
    with tabs[1]:
        st.selectbox('Testing level',['Parameter contract tests (pytest)'])
        st.caption('The existing generator supports parameter contracts. Dedicated HLT, LLT and integration generators are not implemented; connect a system adapter before execution.')
        if st.button('Generate draft tests',type='primary',disabled=not selected):
            subset=deepcopy(contract)
            subset['requirements']=[r for r in requirements if r['id'] in selected]
            subset['parameters']=[p for p in contract['parameters'] if p.get('requirement_id') in selected]
            try:
                output=generate_tests(subset)
                output['input_hash']=digest(st.session_state.tester_editor)
                st.session_state.tester_output=output
                st.session_state.generation_output=output
                st.session_state.pop('generation_review',None)
                save_draft(directory,st.session_state)
            except Exception as exc: st.error(str(exc))
    output=st.session_state.get('generation_output',st.session_state.get('tester_output',{}))
    current=output.get('agent')=='test_generation' and output.get('input_hash')==digest(st.session_state.tester_editor)
    with tabs[2]: table(st,output.get('cases',[]) if current else [])
    with tabs[3]:
        st.caption('Generated tests have not been executed against a system.')
        if current:
            for issue in output.get('unresolved',[]): st.warning(issue)
            table(st,output.get('client_checks',[]))
    with tabs[4]:
        if current:
            reviewer=st.text_input('Export reviewer')
            confirmed=st.checkbox('I reviewed the generated cases and unresolved constraints')
            if st.button('Approve generated draft for export',disabled=not confirmed or not reviewer.strip()):
                st.session_state.generation_review={'digest':digest(json.dumps(output,sort_keys=True)),'reviewer':reviewer,'at':datetime.now(timezone.utc).isoformat()}
                save_draft(directory,st.session_state)
            review=st.session_state.get('generation_review',{})
            if review.get('digest')==digest(json.dumps(output,sort_keys=True)):
                st.download_button('Download pytest draft',output['code'],'test_generated.py','text/x-python')
                st.download_button('Download test cases JSON',json.dumps(output,indent=2),'test-cases.json','application/json')
        else: st.info('Generate and review tests to enable export.')


def render_projects(st,store,client,project):
    st.header('Projects',anchor=False)
    st.caption('Select a project in Project settings. Documents, drafts, runs, and overrides are isolated by client and project.')
    with st.container(border=True):
        st.subheader(project)
        st.write(client['name'])
        table(st,[{'File':d['name'],'Guidance':d.get('guidance',False)} for d in store.documents(client['id'],project)])
        navigate(st,'Continue import draft','Smart Import')
        navigate(st,'Open document library','Document Library')


def render_rules(st,store,client,project):
    st.header('Rules Manager',anchor=False)
    workspace=UniversalStore(store,client['id'],project)
    config=workspace.settings()
    tabs=st.tabs(['Rule Packs','DO-178C','Client Rules','GT44 / Additional Standards','Custom Rules','Rule Conflicts','Execution History'])
    with tabs[0]:
        table(st,[{k:v for k,v in p.items() if k!='rules'} for p in config['rule_packs']])
    for tab,prefix in [(tabs[1],'do-178'),(tabs[2],'client'),(tabs[3],'gt44')]:
        with tab:
            packs=[p for p in config['rule_packs'] if p['id'].lower().startswith(prefix)]
            if packs: st.json(packs)
            else: st.info('No documented pack configured. Supply authoritative definitions before making standards claims.')
    with tabs[4]:
        scope=st.radio('Rule configuration scope',['Project overrides','Client defaults'],horizontal=True)
        raw=st.text_area('Rule packs JSON',json.dumps(config['rule_packs'],indent=2),height=300)
        st.caption('Saving affects future runs. Existing persisted runs keep their configuration snapshot. IDs, versions, source, applicability, severity, and operators use the existing validator.')
        if st.button('Validate & apply rule packs',type='primary'):
            try:
                packs=json.loads(raw)
                validate_settings({**config,'rule_packs':packs})
                if scope=='Project overrides':
                    path=workspace.root/'overrides.json'
                else: path=workspace.client_path
                layer=json.loads(path.read_text('utf-8')) if path.exists() else {}
                workspace.save_settings({**layer,'rule_packs':packs},project=scope=='Project overrides')
                st.success('Validated rule packs saved. Run through Agent Studio to evaluate canonical CIR evidence.')
            except Exception as exc: st.error(str(exc))
    with tabs[5]:
        try:
            validate_settings(config)
            st.success('No conflicts detected by the configured range and prefix checks.')
        except Exception as exc: st.error(str(exc))
        st.caption('This validation does not establish satisfaction of mandatory certification objectives.')
    with tabs[6]:
        table(st,[{'Run':r['id'],'Status':r['status'],'Findings':len(r['findings'])} for r in workspace.runs()])


def render_precision(st,store,client,project):
    st.subheader('Precision & project overrides')
    workspace=UniversalStore(store,client['id'],project)
    config=workspace.settings()
    tabs=st.tabs(['Data Types & Precision','AI Models','Documentation','Export Templates'])
    with tabs[0]:
        scope=st.radio('Precision scope',['Project overrides','Client defaults'],horizontal=True)
        policy=config['precision']
        modes=['decimal_places','significant_digits','binary_bits']
        mode=st.selectbox('Numeric precision mode',modes,index=modes.index(policy['mode']))
        digits=st.number_input('Digits / bit width',1,1024,int(policy['digits']))
        absolute=st.text_input('Absolute comparison tolerance',policy['absolute_tolerance'])
        relative=st.text_input('Relative comparison tolerance',policy['relative_tolerance'])
        proposal={'mode':mode,'digits':digits,'absolute_tolerance':absolute,'relative_tolerance':relative}
        st.json({'current':policy,'proposed':proposal})
        st.caption('Impact: future universal runs use this policy for numeric formatting proposals and equality checks. Original numeric lexemes and existing run snapshots are retained. Parameter-contract checks use their explicit approved constraints.')
        if st.button('Validate & apply precision'):
            try:
                validate_settings({**config,'precision':proposal})
                path=workspace.root/'overrides.json' if scope=='Project overrides' else workspace.client_path
                layer=json.loads(path.read_text('utf-8')) if path.exists() else {}
                workspace.save_settings({**layer,'precision':proposal},project=scope=='Project overrides')
                st.success('Validated precision saved.')
            except Exception as exc: st.error(str(exc))
    with tabs[1]: navigate(st,'Configure independent agents','AI Agent Studio',key='precision-agents')
    with tabs[2]:
        st.caption('Client guidance is maintained in the document library and supplied as untrusted reference material.')
        navigate(st,'Open guidance documents','Document Library',key='precision-library')
    with tabs[3]:
        st.json({'enabled_formats':config['export_formats'],'templates':config['output_templates']})
        st.caption('JSON and CSV are built-in. Additional exports require a registered output adapter.')


def render_reports(st,store,client,project):
    from smartx.universal import export
    st.header('Reports & Traceability',anchor=False)
    workspace=UniversalStore(store,client['id'],project)
    runs=workspace.runs()
    tabs=st.tabs(['Reports Overview','Verification Reports','Requirement Traceability','Execution History','Export Center'])
    with tabs[0]:
        table(st,[{'Run':r['id'],'Status':r['status'],'Requirements':len(r['cir']['requirements']),'Findings':len(r['findings'])} for r in runs])
        st.caption('Universal run exports retain source hashes, configuration snapshots, findings, proposals, and human review.')
    with tabs[1]:
        for run in runs:
            with st.expander(run['id']+' · '+run['status']): table(st,run['findings'])
        result=st.session_state.get('verification_output',st.session_state.get('tester_output',{}))
        if result.get('agent')=='verification' and result.get('input_hash')==digest(st.session_state.get('tester_editor','')):
            table(st,result.get('findings',[]))
            st.download_button('Download constraint verification JSON',json.dumps(result,indent=2),'verification.json','application/json')
    with tabs[2]:
        table(st,[{'Run':r['id'],'Requirement':q['id'],'Source SHA256':q['source_ref']} for r in runs for q in r['cir']['requirements']])
        st.caption('Source lineage is recorded. Agent traceability statements remain proposals until reviewed. No system execution coverage is asserted.')
    with tabs[3]:
        for run in runs:
            with st.expander('History · '+run['id']):
                table(st,run['audit'])
                table(st,run['logs'])
    with tabs[4]:
        eligible=[r for r in runs if r['status']=='approved']
        if not eligible: st.info('Approve a completed run in Agent Studio to enable its exports.')
        for run in eligible:
            for kind in run['configuration']['export_formats']:
                try:
                    data=export(run,kind)
                    st.download_button(f'Export {run["id"][:8]} · {kind.upper()}',data,f'sx-{run["id"]}.{kind}',key='report-'+run['id']+kind)
                except Exception as exc: st.error(str(exc))
        contract=approved_contract(st.session_state)
        if contract:
            st.download_button('Download reviewed parameter contract',json.dumps(contract,indent=2),'canonical-contract.json','application/json')
        navigate(st,'Review generated tests for export','Test Generation',key='reports-generation')
