"""Standards API adapter; reuses scope, role configuration and human gates."""
import base64
from copy import deepcopy
import json
import os
from jsonschema import Draft202012Validator
from agents.universal import OllamaAgents
from smartx.aerospace_standards import StandardsStore, require_admin, EXTRACTION_SCHEMA, identity
from smartx.universal import UniversalStore


def source_evidence(platform,data):
    from FRONTED.ui.workspace_assistant import evidence_for
    from smartx.engineering_workflow import EngineeringWorkflow
    state=platform.state(data)
    _,_,directory=platform.scope(data)
    workflow=EngineeringWorkflow(directory,state['client']['revision']).load()
    return state,evidence_for(state,workflow,data.get('prompt',''))


def inference(platform,data,operation):
    with platform.lock:
        client,project,directory=platform.scope(data)
        store=StandardsStore(directory); state=store.load()
        config=deepcopy(UniversalStore(platform.store,client,project).settings()['agents'][
            'standards_retrieval' if operation=='extract' else 'orchestrator'])
        if not config.get('model'): raise ValueError('Assign a verified installed Qwen model in AI Agent Studio')
        before=identity(state)
        question=data.get('prompt','')
        hits=store.retrieve(question)
        if not hits: raise ValueError('No matching uploaded standards evidence. Upload or review the authorized source first.')
        evidence={h['id']:h for h in hits}
        if operation=='extract':
            require_admin(data.get('admin_token'))
            config['schema']=EXTRACTION_SCHEMA
            task='Act as the Standards Rule Extraction Agent. Propose only source-backed rules using exact source_quote substrings and supplied source_ref IDs. Do not infer missing clauses, DAL applicability, objective numbers or expected behavior. Empty DAL means unknown. Categories distinguish machine presence checks from engineering judgments. Proposed logic is descriptive text, never executable code. Only propose deterministic checks when the source explicitly supports them. No activation or approval.'
        else:
            selected,project_evidence=source_evidence(platform,data)
            project_before=identity({'draft':selected['draft'],'workflow':selected['workflow'],'settings':selected['settings']})
            # Keep only bounded project evidence; standard chunks are already bounded.
            evidence.update(project_evidence)
            config['schema']={'type':'object','additionalProperties':False,'required':['answer','citations','limitations'],
                'properties':{'answer':{'type':'string','minLength':1,'maxLength':6000},
                'citations':{'type':'array','minItems':1,'uniqueItems':True,'items':{'enum':list(evidence)}},
                'limitations':{'type':'array','items':{'type':'string'}}}}
            task='Answer only aerospace questions about supplied standards and the selected project. Every standards claim needs a precise uploaded standards citation; every project-specific claim needs project evidence citations. Separate evidence from interpretation. Reference ebooks are explanatory guidance, not verified mandatory standard clauses. Unknown applicability or missing evidence must be explicit. Never claim certification or successful test execution.'
        config.update(retries=0,timeout=600,num_ctx=8192,num_gpu=int(os.getenv('SX_ASSISTANT_NUM_GPU','0')))
        config['system_prompt']+='\n'+task
        context={'question':question,'dal':state['dal'],'evidence':evidence,
                 'approved_rules':[r for r in state['rules'] if r['review_status']=='approved'][:12]}
        if len(json.dumps(context))>60000: raise ValueError('Narrow the standards question to reduce context')
    logs=[]
    service=OllamaAgents(os.getenv('OLLAMA_ENDPOINT','http://localhost:11434'))
    result=service.execute('standards_retrieval' if operation=='extract' else 'orchestrator',config,context,logs,output_limit=2400 if operation=='extract' else 1024)
    Draft202012Validator(config['schema']).validate(result)
    with platform.lock:
        if before!=identity(store.load()): raise ValueError('Standards changed during inference; retry with current sources')
        if operation=='extract':
            rules=store.propose(result['rules'])
            return {'rules':rules,'limitations':result['limitations'],'model':config['model'],'logs':logs}
        current=platform.state(data)
        if project_before!=identity({'draft':current['draft'],'workflow':current['workflow'],'settings':current['settings']}):
            raise ValueError('Project changed during standards inference; ask again')
        if not any(ref in {h['id'] for h in hits} for ref in result['citations']):
            raise ValueError('Standards answer lacks an uploaded source citation')
        if any(ref not in evidence for ref in result['citations']): raise ValueError('Unsupported standards citation')
        return {**result,'scope':'project','provider':'ollama','model':config['model'],
            'citations':[{'id':ref,'name':evidence[ref].get('name',ref),
                          **{k:evidence[ref][k] for k in ('document','version','page','section','table','document_hash','authority') if k in evidence[ref]}} for ref in result['citations']],
            'logs':logs}


def action(platform,operation,data):
    if operation.startswith('engineering-'):
        from FRONTED.ui.rule_engineering_workspace import action as engineering_action
        return engineering_action(platform,operation.removeprefix('engineering-'),data)
    if operation in ('extract','assistant'): return inference(platform,data,operation)
    with platform.lock:
        client,project,directory=platform.scope(data); store=StandardsStore(directory)
        if operation=='state': return store.public()
        if operation=='search': return {'results':store.retrieve(data.get('query',''))}
        if operation=='document':
            doc,extraction=store.extracted(store.load(),data['document'])
            return {'document':doc,'extraction':extraction}
        if operation=='check':
            from smartx.engineering_workflow import EngineeringWorkflow
            state=platform.state(data)
            if state['workflow'].get('review_current'):
                datasets=EngineeringWorkflow(directory,state['client']['revision']).load()['extraction']['datasets']
            elif state['approved']:
                datasets=platform.contract(directory,client,project)[1]
            else: raise ValueError('Review and approve current project evidence before Aerospace Smart Check')
            from FRONTED.ui.rule_engineering_workspace import project_evidence
            _,_,known=project_evidence(platform,data,True)
            result=store.check(datasets,state.get('project_detail',{}).get('activity'),known,state['project_detail'].get('configuration',{}))
            platform.store._atomic(directory/'aerospace-check.json',json.dumps(result,indent=2).encode())
            return result
        require_admin(data.get('admin_token'))
        if 'expected_revision' in data and data['expected_revision']!=store.load()['revision']:
            raise ValueError('Standards changed in another session; refresh before reviewing or editing')
        reviewer=data.get('reviewer','').strip()
        if operation=='upload':
            blob=base64.b64decode(data.get('data',''),validate=True)
            result=store.ingest(data['name'],blob,data.get('version',''),data.get('authority','reference'),reviewer,data.get('supersedes'),data.get('source_metadata'))
            return {'document':result,'standards':store.public()}
        if operation=='dal': store.set_dal(data.get('dal'),reviewer,data.get('rationale',''))
        elif operation=='propose':
            if not reviewer: raise ValueError('Named administrator required')
            store.propose(data.get('rules',[]),reviewer)
        elif operation=='revise':store.revise_rule(data['rule'],data['proposal'],reviewer,data.get('rationale',''))
        elif operation=='review':
            if data.get('decision') in ('approve','activate'):raise ValueError('Legacy approval activates executable logic; migrate to an authenticated, qualified engineered rule')
            effective=platform.project_store.effective(client,project)
            client_rules=list(effective.get('rules',[]))
            for pack in UniversalStore(platform.store,client,project).settings()['rule_packs']:
                if pack['active']: client_rules.extend(pack['rules'])
            store.review_rule(data['rule'],data['decision'],reviewer,data.get('rationale',''),data.get('applicability_confirmed') is True,client_rules)
        elif operation=='table': store.review_table(data['document'],data['table'],data['cells'],reviewer,data.get('rationale',''))
        elif operation=='reindex': store.reindex()
        elif operation=='map':
            from smartx.engineering_workflow import EngineeringWorkflow
            workflow=EngineeringWorkflow(directory,platform.project_store.effective(client,project)['revision']).load()
            known={d['hash'] for d in platform.store.documents(client,project)}|{s['id'] for s in workflow.get('sources',[])}
            store.map_evidence(data['rule'],data['source_ref'],data.get('record_id',''),reviewer,known)
        else: raise ValueError('Unknown Aerospace Standards operation')
        # Existing exported candidates become stale after any governance change.
        from smartx.engineering_workflow import EngineeringWorkflow
        workflow_engine=EngineeringWorkflow(directory,platform.project_store.effective(client,project)['revision'])
        workflow=workflow_engine.load()
        if workflow.get('generation'):
            workflow.pop('generation',None); workflow_engine.save(workflow)
        draft=platform.draft(directory)
        if 'generation_review' in draft:
            draft.pop('generation_review'); platform.save(directory,draft)
        return store.public()
