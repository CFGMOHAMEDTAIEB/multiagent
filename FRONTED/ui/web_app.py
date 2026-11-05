"""SX Aerospace web UI. Reuses the existing engineering backend; loopback only."""
from __future__ import annotations
import argparse
import base64
from copy import deepcopy
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
import threading
from urllib.parse import urlsplit, parse_qs

from smartx.clients import ClientStore, bind_client
from smartx.projects import Projects
from smartx.engineering_workflow import EngineeringWorkflow
from agents import local_models
from agents.local_models import test_agent
from smartx.universal import merge
from smartx.testing import canonicalize, validate_contract, verify, generate_tests
from smartx.universal import UniversalStore, new_run, execute, approve, reject, recover, export
from agents.universal import OllamaAgents, ROLES
from llm.router import LLMRouter
from FRONTED.ui.redesign import digest, approved_contract

ROOT = Path(__file__).resolve().parents[1]
STATIC = Path(__file__).parent / 'web'


class Platform:
    def __init__(self, directory=None):
        self.store = ClientStore(directory or ROOT / '.smartx_clients')
        self.lock = threading.RLock()
        self.project_store = Projects(self.store)
        self.downloads = local_models.ModelDownloads()
        from smartx.agentic_assistant import EngineeringAssistant
        self.engineering_assistant = EngineeringAssistant(self)
        from smartx.reviewer_auth import ReviewerAuth
        self.reviewer_auth = ReviewerAuth(self.store.directory)

    def scope(self, data):
        client_id = data.get('client', 'default')
        self.store.get(client_id)
        project = data.get('project', 'default')
        if not isinstance(project, str) or not project.strip() or len(project) > 200:
            raise ValueError('Project name must contain 1–200 characters')
        return client_id, project, self.store.project_directory(client_id, project)

    def draft(self, directory):
        path = directory / 'ui-draft.json'
        return json.loads(path.read_text('utf-8')) if path.exists() else {}

    def save(self, directory, draft):
        self.store._atomic(directory / 'ui-draft.json', json.dumps(draft, ensure_ascii=False, indent=2).encode())

    def contract(self, directory, client_id, project):
        state = self.draft(directory)
        client = self.project_store.effective(client_id, project)
        state['workspace_scope'] = (client_id, client['revision'], project, client['profile'])
        contract = approved_contract(state)
        if contract is None:
            raise ValueError('Review and approve the current canonical JSON before proceeding')
        return state, deepcopy(contract)

    def projects(self, client_id):
        return self.project_store.list(client_id)

    def state(self, data):
        client_id, project, directory = self.scope(data)
        workspace = UniversalStore(self.store, client_id, project)
        draft = self.draft(directory)
        client = self.project_store.effective(client_id, project)
        scoped = {**draft, 'workspace_scope': (client_id, client['revision'], project, client['profile'])}
        from smartx.aerospace_standards import StandardsStore
        knowledge=StandardsStore(directory).load()
        return {'clients': self.store.list(), 'client': client, 'project': project,
                'aerospace_context':{'revision':knowledge['revision'],'dal':knowledge['dal']},
                'projects': self.projects(client_id), 'project_detail': self.project_store.get(client_id, project), 'draft': draft,
                'approved': approved_contract(scoped) is not None,
                'workflow': EngineeringWorkflow(directory, client['revision']).public(),
                'documents': self.store.documents(client_id, project),
                'model_tests': json.loads((directory/'model-diagnostics.json').read_text('utf-8')) if (directory/'model-diagnostics.json').exists() else {},
                'settings': workspace.settings(), 'roles': list(ROLES), 'runs': workspace.runs()}

    def propose_workflow(self, data):
        from uuid import uuid4
        from smartx.workflow_prompting import propose, configuration_digest
        from smartx.engineering_workflow import timestamp
        with self.lock:
            client, project, directory = self.scope(data)
            revision = self.project_store.effective(client, project)['revision']
            engine = EngineeringWorkflow(directory, revision)
            snapshot = engine.load()
            prompt = data.get('prompt','')
            if not isinstance(prompt,str) or not prompt.strip() or len(prompt)>8000:
                raise ValueError('Describe your workflow in 1 to 8000 characters')
            config = deepcopy(UniversalStore(self.store, client, project).settings()['agents']['json_transformation'])
            if not config.get('model'): raise ValueError('Assign an installed model to the Data Structuring agent in AI Agent Studio first')
            config['retries'] = 0
            request_id = uuid4().hex
            base = configuration_digest(snapshot,revision)
            snapshot['prompting'] = {'mode':'prompt','prompt':prompt,'model':config['model'],'status':'running','request_id':request_id,'started_at':timestamp()}
            engine.save(snapshot)
        try:
            proposal, logs = propose(OllamaAgents(os.getenv('OLLAMA_ENDPOINT','http://localhost:11434')), config, prompt, snapshot,activity=self.project_store.get(client,project)['activity'])
        except Exception as exc:
            with self.lock:
                current=engine.load()
                if current.get('prompting',{}).get('request_id')==request_id:
                    current['prompting'].update(status='failed',error=str(exc),completed_at=timestamp())
                    engine.save(current)
            raise ValueError('Configuration inference failed: '+str(exc)) from exc
        with self.lock:
            current=engine.load()
            if current.get('prompting',{}).get('request_id')!=request_id:
                raise ValueError('A newer prompt replaced this request')
            revision_now=self.project_store.effective(client, project)['revision']
            if configuration_digest(current,revision_now)!=base:
                current['prompting'].update(status='stale',error='Workflow changed during inference. Generate a new proposal.')
                engine.save(current)
                raise ValueError('Workflow changed during inference. Generate a new proposal.')
            current['prompting'].update(status='ready',proposal=proposal,base_digest=base,completed_at=timestamp(),inference={'model':config['model'],'schema_validated':True,'duration_seconds':sum(item.get('duration_seconds',0) for item in logs)})
            engine.save(current)
            return self.state(data)

    def assistant(self, data):
        from FRONTED.ui.workspace_assistant import answer
        from smartx.engineering_workflow import fingerprint
        def snapshot(state,workflow):
            return fingerprint({'revision':state['client']['revision'],'draft':state['draft'],
                'models':{r:c.get('model') for r,c in state['settings']['agents'].items()},
                'workflow':{k:v for k,v in workflow.items() if k not in ('prompting','updated_at')}})
        with self.lock:
            client, project, directory = self.scope(data)
            state = self.state(data)
            workflow = EngineeringWorkflow(directory, state['client']['revision']).load()
            config = deepcopy(state['settings']['agents']['orchestrator'])
            before = snapshot(state,workflow)
        # Local inference must not lock project uploads, edits or the rest of the UI.
        result = answer(OllamaAgents(os.getenv('OLLAMA_ENDPOINT','http://localhost:11434')), config, state, workflow,
                        data.get('prompt',''), data.get('page','dashboard'), data.get('history'))
        with self.lock:
            current = self.state(data)
            if before != snapshot(current,EngineeringWorkflow(directory,current['client']['revision']).load()):
                raise ValueError('Project data or configuration changed while the assistant was answering. Ask again to use the current evidence.')
        return result

    def action(self, action, data):
        if action.startswith('prompt-'):
            from smartx.prompt_workspace import action as prompt_action
            return prompt_action(self,action.removeprefix('prompt-'),data)
        if action.startswith('operational-'):
            from FRONTED.ui.operational_verification import action as operational_action
            return operational_action(self,action.removeprefix('operational-'),data)
        if action.startswith('reviewer-'):
            with self.lock:
                client,project,_=self.scope(data)
                return self.reviewer_auth.action(client,project,action.removeprefix('reviewer-'),data)
        if action.startswith('standards-'):
            from FRONTED.ui.standards_workspace import action as standards_action
            return standards_action(self, action.removeprefix('standards-'), data)
        if action == 'assistant':
            import re
            if re.search(r'(?i)DO[- ]?178|\bDAL\b|MC/DC|standards? objective',data.get('prompt','')):
                from FRONTED.ui.standards_workspace import action as standards_action
                return standards_action(self,'assistant',data)
            if data.get('agentic') is True:
                return self.engineering_assistant.start(data)
            return self.assistant(data)
        if action == 'assistant-review':
            return self.engineering_assistant.review(data)
        if action == 'assistant-retry':
            return self.engineering_assistant.retry(data)
        if action == 'assistant-apply':
            return self.engineering_assistant.apply(data)
        if action == 'assistant-revert':
            return self.engineering_assistant.revert(data)
        if action == 'workflow-propose':
            return self.propose_workflow(data)
        with self.lock:
            client_id, project, directory = self.scope(data)
            workspace = UniversalStore(self.store, client_id, project)
            draft = self.draft(directory)
            if action == 'import' and not (directory / 'project.json').exists():
                self.project_store.save(client_id, project, {})
            context = self.store.context(client_id, project)
            effective = self.project_store.effective(client_id, project)
            context.update({k:effective[k] for k in context if k in effective})
            detail = self.project_store.get(client_id, project)
            if action == 'verify' and detail['process'] in ('generation','import'):
                raise ValueError('Smart Check is not enabled for this project')
            profiles = {'LLR':'low_level_requirements','LLT':'low_level_tests','HLT':'high_level_tests'}
            if action == 'verify' and data.get('verification_profile', profiles[detail['activity']]) != profiles[detail['activity']]:
                raise ValueError('Check profile must match the project activity')
            if action == 'generate' and data.get('level', detail['activity']) != detail['activity']:
                raise ValueError('Generation level must match the project activity')
            if action == 'generate' and detail['process'] in ('verification','import'):
                raise ValueError('This project only enables verification or import')
            if action.startswith('workflow-'):
                operation = action.removeprefix('workflow-')
                if operation == 'check' and detail['process'] not in ('verification','workflow'):
                    raise ValueError('Enable Smart Check or Complete Workflow in project settings')
                if operation in ('generate','review-generation') and detail['process'] not in ('generation','workflow'):
                    raise ValueError('Enable Smart Generate or Complete Workflow in project settings')
                EngineeringWorkflow(directory, effective['revision']).action(operation, data)
                if operation == 'check':
                    from smartx.aerospace_standards import StandardsStore
                    engine=EngineeringWorkflow(directory,effective['revision'])
                    current=engine.load()
                    known={d['hash'] for d in self.store.documents(client_id,project)}|{s['id'] for s in current['sources']}
                    current['checks']['aerospace']=StandardsStore(directory).check(current['extraction']['datasets'],detail['activity'],known,detail.get('configuration',{}))
                    engine.save(current)
                applied_setup = EngineeringWorkflow(directory,effective['revision']).load().get('setup',{})
                if operation in ('setup','apply-prompt') and applied_setup.get('activity',detail['activity']) != detail['activity']:
                    self.project_store.save(client_id, project, {'activity':applied_setup['activity']})
                return self.state(data)
            if action in ('project', 'project-update'):
                self.project_store.save(client_id, project, data.get('details', {}), create=action == 'project')
            elif action == 'project-delete':
                self.project_store.delete(client_id, project)
                return {'projects': self.projects(client_id), 'deleted': project}
            elif action == 'project-configuration':
                self.project_store.save(client_id, project, {'configuration': data['profile']})
            elif action == 'import':
                files = data.get('files', [])
                if not files or len(files) > 50:
                    raise ValueError('Select between 1 and 50 source files')
                sources = []
                for item in files:
                    name = Path(item['name'].replace('\\', '/')).name
                    blob = base64.b64decode(item['data'], validate=True)
                    if len(blob) > 10 * 1024 * 1024:
                        raise ValueError(name + ': exceeds the 10 MB file limit')
                    sources.append((name, blob))
                if sum(len(blob) for _, blob in sources) > 50 * 1024 * 1024:
                    raise ValueError('Combined upload exceeds 50 MB')
                provider = data.get('provider', 'deterministic')
                if provider not in ('deterministic', 'ollama'):
                    raise ValueError('Qwen-only policy: select local Ollama or deterministic processing')
                router = LLMRouter(provider)
                normalized = canonicalize(sources, router, context)
                draft = {'tester_json': normalized, 'tester_editor': json.dumps(normalized, ensure_ascii=False, indent=2, default=str), 'import_step': 1}
                self.save(directory, draft)
                for name, blob in sources:
                    self.store.add_document(client_id, project, name, blob, guidance=bool(data.get('guidance')))
                if not (directory / 'project.json').exists():
                    self.project_store.save(client_id, project, {})
            elif action == 'draft':
                text = data['text']
                if len(text) > 15 * 1024 * 1024:
                    raise ValueError('Canonical JSON exceeds the editor limit')
                if text != draft.get('tester_editor'):
                    for key in ('tester_approved', 'tester_output', 'verification_output', 'generation_output', 'generation_review'):
                        draft.pop(key, None)
                draft['tester_editor'] = text
                draft['import_step'] = int(data.get('step', 2))
                self.save(directory, draft)
            elif action == 'approve':
                contract = bind_client(validate_contract(json.loads(draft['tester_editor'])), context)
                reviewer = data.get('reviewer', '').strip()
                if not reviewer:
                    raise ValueError('Enter a reviewer name')
                contract.setdefault('audit', []).append({'agent': 'human_review', 'reviewer': reviewer, 'decision': 'approve', 'at': datetime.now(timezone.utc).isoformat()})
                draft['tester_approved'] = {'hash': digest(draft['tester_editor']), 'contract': contract}
                draft['import_step'] = 3
                self.save(directory, draft)
            elif action in ('verify', 'generate'):
                draft, contract = self.contract(directory, client_id, project)
                if action == 'generate':
                    selected = set(data.get('requirements', []))
                    known = {r['id'] for r in contract['requirements']}
                    if not selected or not selected <= known:
                        raise ValueError('Select valid requirements to generate tests')
                    contract['requirements'] = [r for r in contract['requirements'] if r['id'] in selected]
                    contract['parameters'] = [p for p in contract['parameters'] if p.get('requirement_id') in selected]
                output = verify(contract) if action == 'verify' else generate_tests(contract)
                from smartx.aerospace_standards import StandardsStore, enrich_cases
                standards=StandardsStore(directory)
                known={d['hash'] for d in self.store.documents(client_id,project)}
                if action == 'verify': output['aerospace']=standards.check(contract,detail['activity'],known,detail.get('configuration',{}))
                else:
                    target_level={'HLR':'HLT','LLR':'LLT'}.get(detail['activity'],detail['activity'])
                    enrich_cases(output,standards,target_level,effective)
                    from smartx.rule_engineering import EngineeringStore
                    output['aerospace']['generated_rule_checks']=EngineeringStore(standards).check(
                        {**contract,'test_cases':output['cases']},target_level,known,detail.get('configuration',{}))
                output['input_hash'] = digest(draft['tester_editor'])
                output['review'] = contract.get('audit', [])
                draft['tester_output'] = output
                draft['verification_output' if action == 'verify' else 'generation_output'] = output
                if action == 'generate':
                    draft.pop('generation_review', None)
                self.save(directory, draft)
            elif action == 'review-generation':
                draft, _ = self.contract(directory, client_id, project)
                output = draft.get('generation_output')
                reviewer = data.get('reviewer', '').strip()
                if not reviewer or not output or output['input_hash'] != digest(draft['tester_editor']):
                    raise ValueError('Current generated tests and a named reviewer are required')
                from smartx.aerospace_standards import StandardsStore
                if output.get('aerospace',{}).get('knowledge_revision',0)!=StandardsStore(directory).load()['revision']:
                    raise ValueError('Standards changed; regenerate tests before review')
                findings=output.get('aerospace',{}).get('generated_rule_checks',{}).get('findings',[])
                if any(f['status'] in ('FAIL','INSUFFICIENT_EVIDENCE') for f in findings):
                    raise ValueError('Generated tests fail an active engineered rule or lack required evidence; resolve findings before approval')
                draft['generation_review'] = {'reviewer': reviewer, 'digest': digest(json.dumps(output, sort_keys=True)), 'at': datetime.now(timezone.utc).isoformat()}
                self.save(directory, draft)
            elif action == 'finding-review':
                draft, _ = self.contract(directory, client_id, project)
                output = draft.get('verification_output', {})
                index = int(data['index'])
                if not data.get('reviewer', '').strip() or not 0 <= index < len(output.get('findings', [])):
                    raise ValueError('Select a finding and enter a reviewer')
                if data.get('decision') not in ('Reviewed', 'Needs correction', 'Rejected'):
                    raise ValueError('Invalid review decision')
                draft.setdefault('finding_reviews', []).append({'finding': index, 'input_hash': output['input_hash'], 'reviewer': data['reviewer'], 'decision': data['decision'], 'comment': data.get('comment', ''), 'at': datetime.now(timezone.utc).isoformat()})
                self.save(directory, draft)
            elif action == 'client':
                self.store.save({**self.store.get(client_id), **data['profile'], 'id': client_id})
            elif action == 'create-client':
                created = self.store.save(data['profile'])
                return {'created_client': created['id']}
            elif action == 'settings':
                patch = data['settings']
                if 'agents' in patch:
                    for role, proposed in patch['agents'].items():
                        if proposed.get('model') and proposed.get('model') != workspace.settings()['agents'][role]['model']:
                            OllamaAgents(os.getenv('OLLAMA_ENDPOINT', 'http://localhost:11434')).inspect(proposed['model'])
                project_scope = data.get('scope', 'project') == 'project'
                path = workspace.root / 'overrides.json' if project_scope else workspace.client_path
                layer = json.loads(path.read_text('utf-8')) if path.exists() else {}
                workspace.save_settings(merge(workspace.settings(), patch) if project_scope else {**layer, **patch}, project=project_scope)
            elif action == 'models':
                return local_models.discover()
            elif action == 'assign-model':
                model = data['model']
                OllamaAgents(os.getenv('OLLAMA_ENDPOINT', 'http://localhost:11434')).inspect(model)
                agents = workspace.settings()['agents']
                for config in agents.values():
                    config['model'] = model
                path = workspace.root / 'overrides.json'
                layer = json.loads(path.read_text('utf-8')) if path.exists() else {}
                workspace.save_settings({**layer, 'agents': agents}, project=True)
            elif action == 'test-agent':
                role = data['role']
                if role not in ROLES:
                    raise ValueError('Unknown agent role')
                try:
                    result = test_agent(role, workspace.settings()['agents'][role])
                except Exception as exc:
                    result = {'role':role, 'status':'failed', 'error':str(exc)}
                path = directory / 'model-diagnostics.json'
                diagnostics = json.loads(path.read_text('utf-8')) if path.exists() else {}
                diagnostics[role] = result
                self.store._atomic(path, json.dumps(diagnostics, indent=2).encode())
                return {'diagnostic':result, 'state':self.state(data)}
            elif action == 'start-ollama':
                return local_models.start_service(directory / 'ollama')
            elif action == 'pull-model':
                from smartx.aerospace_standards import require_admin
                require_admin(data.get('admin_token'))
                return self.downloads.start(data['model'])
            elif action == 'pull-status':
                return self.downloads.status(data['id'])
            elif action == 'new-run':
                sources = []
                for source in data.get('documents', []):
                    record = next((d for d in self.store.documents(client_id, project) if d['hash'] == source), None)
                    if not record:
                        raise ValueError('Unknown source document')
                    sources.append((record['name'], (directory / 'library' / record['hash'] / 'original.bin').read_bytes()))
                run = new_run(sources, workspace.settings(), context)
                workspace.save(run)
            elif action in ('execute-run', 'approve-run', 'reject-run', 'recover-run'):
                run = next((r for r in workspace.runs() if r['id'] == data['run']), None)
                if not run:
                    raise ValueError('Unknown run')
                if action == 'execute-run':
                    if run['status'] not in ('ready', 'failed'):
                        raise ValueError('Run is not ready for execution')
                    from smartx.aerospace_standards import StandardsStore
                    standards=StandardsStore(directory)
                    knowledge=standards.load()
                    run['standards_context']={'revision':knowledge['revision'],'dal':knowledge['dal'],
                        'rules':[r for r in knowledge['rules'] if r['active']],
                        'citations':standards.retrieve('software requirements verification traceability') if knowledge['documents'] else []}
                    execute(run, OllamaAgents(os.getenv('OLLAMA_ENDPOINT', 'http://localhost:11434')), checkpoint=workspace.save)
                elif action == 'approve-run':
                    from smartx.aerospace_standards import StandardsStore
                    if run.get('standards_context',{}).get('revision',0)!=StandardsStore(directory).load()['revision']:
                        raise ValueError('Standards changed; recover and rerun before approval')
                    approve(run, data.get('reviewer', ''))
                elif action == 'reject-run': reject(run, data.get('reviewer', ''), data.get('reason', ''))
                else:
                    from smartx.aerospace_standards import StandardsStore
                    current_revision=StandardsStore(directory).load()['revision']
                    if run.get('standards_context',{}).get('revision',0)!=current_revision:
                        run['audit'].append({'event':'standards_invalidated','previous_status':run['status'],'knowledge_revision':current_revision})
                        run.update(status='rejected',review=None)
                    recover(run, workspace.settings())
                workspace.save(run)
            else:
                raise ValueError('Unknown operation')
            return self.state(data)

    def download(self, data):
        client_id, project, directory = self.scope(data)
        kind = data.get('kind', 'contract')
        if kind == 'engineering':
            return EngineeringWorkflow(directory, self.project_store.effective(client_id, project)['revision']).download()
        draft, contract = self.contract(directory, client_id, project)
        if kind == 'contract':
            return 'canonical.json', json.dumps(contract, indent=2, ensure_ascii=False).encode()
        if kind == 'verification':
            output = draft.get('verification_output')
            if not output or output['input_hash'] != digest(draft['tester_editor']):
                raise ValueError('Run verification for the current contract first')
            return 'verification.json', json.dumps(output, indent=2).encode()
        if kind in ('tests', 'code'):
            output = draft.get('generation_output')
            if not output or output['input_hash'] != digest(draft['tester_editor']) or draft.get('generation_review', {}).get('digest') != digest(json.dumps(output, sort_keys=True)):
                raise ValueError('Current generated tests require human review before export')
            from smartx.aerospace_standards import StandardsStore
            if output.get('aerospace',{}).get('knowledge_revision',0)!=StandardsStore(directory).load()['revision']:
                raise ValueError('Standards changed; regenerate and review tests before export')
            return ('test_generated.py', output['code'].encode()) if kind == 'code' else ('test-cases.json', json.dumps(output, indent=2).encode())
        raise ValueError('Unsupported export')


def make_handler(platform):
    class Handler(BaseHTTPRequestHandler):
        def send(self, status, body, content_type='application/json; charset=utf-8', filename=None):
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'self'; object-src 'none'; base-uri 'self'")
            if filename:
                from urllib.parse import quote
                safe_name=''.join(c if 32<=ord(c)<127 and c not in '\\"' else '_' for c in filename)
                self.send_header('Content-Disposition', f'attachment; filename="{safe_name}"; filename*=UTF-8\'\'{quote(filename,safe="")}')
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            try:
                parsed = urlsplit(self.path)
                data = {k: v[0] for k, v in parse_qs(parsed.query).items()}
                if parsed.path == '/api/state':
                    self.send(200, json.dumps(platform.state(data), default=str).encode())
                elif parsed.path == '/api/prompt-download':
                    from smartx.prompt_workspace import PromptWorkspace
                    name,body=PromptWorkspace(platform,data).download(data)
                    self.send(200,body,'application/octet-stream',name)
                elif parsed.path == '/api/prompt-source':
                    from smartx.prompt_workspace import PromptWorkspace
                    name,body=PromptWorkspace(platform,data).source(data)
                    self.send(200,body,'application/octet-stream',name)
                elif parsed.path == '/api/standards-source':
                    if self.headers.get('Host','') not in (f'localhost:{self.server.server_port}',f'127.0.0.1:{self.server.server_port}'):
                        self.send(403,b'{"error":"Local source access only"}'); return
                    from smartx.aerospace_standards import StandardsStore
                    _,_,directory=platform.scope(data)
                    store=StandardsStore(directory)
                    doc=store.document(store.load(),data['document'])
                    self.send(200,(store.version_path(doc)/'original.pdf').read_bytes(),'application/pdf')
                elif parsed.path == '/api/assistant-run':
                    self.send(200, json.dumps(platform.engineering_assistant.get(data), default=str).encode())
                elif parsed.path == '/api/assistant-history':
                    self.send(200, json.dumps(platform.engineering_assistant.history(data), default=str).encode())
                elif parsed.path == '/api/assistant-export':
                    name, body = platform.engineering_assistant.export(data)
                    self.send(200, body, 'application/json', name)
                elif parsed.path == '/api/download':
                    name, body = platform.download(data)
                    self.send(200, body, mimetypes.guess_type(name)[0] or 'application/octet-stream', name)
                elif parsed.path == '/api/run-export':
                    client, project, directory = platform.scope(data)
                    workspace = UniversalStore(platform.store, client, project)
                    run = next(r for r in workspace.runs() if r['id'] == data['run'])
                    from smartx.aerospace_standards import StandardsStore
                    if run.get('standards_context',{}).get('revision',0)!=StandardsStore(directory).load()['revision']:
                        raise ValueError('Standards changed; recover and rerun before export')
                    kind = data.get('kind', 'json')
                    body = export(run, kind)
                    self.send(200, body, 'application/octet-stream', f'run-{run["id"]}.{kind}')
                else:
                    react_root = ROOT / 'web-react'
                    asset = (react_root / parsed.path.lstrip('/')).resolve()
                    if parsed.path == '/':
                        asset = react_root / 'index.html'
                    if asset.is_relative_to(react_root.resolve()) and asset.is_file():
                        self.send(200, asset.read_bytes(), mimetypes.guess_type(asset.name)[0] or 'application/octet-stream')
                        return
                    names = {'/': 'index.html', '/app.css': 'app.css', '/app.js': 'app.js', '/aircraft.svg': 'aircraft.svg'}
                    name = names.get(parsed.path)
                    if not name:
                        self.send(404, b'{"error":"Not found"}')
                        return
                    self.send(200, (STATIC / name).read_bytes(), (mimetypes.guess_type(name)[0] or 'text/plain') + '; charset=utf-8')
            except (ValueError, KeyError, StopIteration, OSError) as exc:
                self.send(400, json.dumps({'error': str(exc)}).encode())

        def do_POST(self):
            try:
                origin = self.headers.get('Origin')
                host = self.headers.get('Host', '')
                if host not in (f'localhost:{self.server.server_port}', f'127.0.0.1:{self.server.server_port}') or (origin and urlsplit(origin).netloc != host):
                    self.send(403, b'{"error":"Same-origin local requests only"}')
                    return
                if self.headers.get_content_type() != 'application/json':
                    raise ValueError('JSON request required')
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 72 * 1024 * 1024:
                    raise ValueError('Request size outside allowed limits')
                data = json.loads(self.rfile.read(length))
                action = self.path.removeprefix('/api/')
                result = platform.action(action, data)
                self.send(200, json.dumps(result, default=str).encode())
            except Exception as exc:
                self.send(400, json.dumps({'error': str(exc)}).encode())
    return Handler


def main():
    parser = argparse.ArgumentParser(description='SX Aerospace web interface')
    parser.add_argument('--port', type=int, default=8501)
    parser.add_argument('--data-dir', type=Path)
    args = parser.parse_args()
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / '.env', override=False)
    except ImportError:
        pass
    server = ThreadingHTTPServer(('127.0.0.1', args.port), make_handler(Platform(args.data_dir)))
    print(f'SX Aerospace: http://localhost:{args.port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
