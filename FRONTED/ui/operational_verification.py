"""Operational coordinator delegating existing import, assistant, review and check services."""
from copy import deepcopy
import json
from uuid import uuid4
from smartx.clients import ClientStore
from smartx.engineering_workflow import EngineeringWorkflow,DATASETS,CHECKS
from smartx.aerospace_standards import identity,now
from smartx.rule_engineering import EngineeringStore
from smartx.rule_qualification import evaluator_version
from FRONTED.ui.rule_engineering_workspace import project_evidence

def files(platform,data):
    client,project,directory=platform.scope(data)
    return directory,directory/'operational-verification.json'

def load(platform,data):
    _,path=files(platform,data)
    return json.loads(path.read_text('utf-8')) if path.exists() else {'schema_version':'sx-operational-1','events':[],'runs':[],'finding_reviews':[]}

def event(platform,data,stage,status,result=None,error=None):
    _,path=files(platform,data);state=load(platform,data)
    state['events'].append({'id':uuid4().hex,'stage':stage,'status':status,'at':now(),'result':result,'error':error})
    state['events']=state['events'][-500:]
    ClientStore._atomic(path,json.dumps(state,indent=2).encode())

def snapshot(platform,data):
    state,datasets,known=project_evidence(platform,data)
    workflow=EngineeringWorkflow(platform.scope(data)[2],state['client']['revision']).load()
    if workflow.get('extraction'):datasets=workflow['extraction']['datasets']
    engine=EngineeringStore(platform.scope(data)[2]);knowledge=engine.load()
    return {'digest':identity({'datasets':datasets,'sources':sorted(known),'client_revision':state['client']['revision'],
        'knowledge_revision':knowledge['revision'],'project_configuration':state['project_detail'].get('configuration',{}),
        'precision':state['settings']['precision'],'check_config':workflow.get('check_config'),
        'evaluator_version':evaluator_version()}),'datasets':datasets,'known':known,'state':state,'knowledge':knowledge}

def traceability(platform,data):
    view=snapshot(platform,data);datasets=view['datasets'];engine=EngineeringStore(platform.scope(data)[2])
    execution=engine.check(datasets,view['state']['project_detail']['activity'],view['known'],view['state']['project_detail'].get('configuration',{}),persist=False)
    evidence=engine.verified_coverage(view['knowledge'],view['known']);results=engine.approved_results({'coverage_evidence':evidence})
    requirements=datasets.get('requirements',[]);tests=datasets.get('test_cases',[]);ids={str(r['id']) for r in requirements if r.get('id')}
    chains=[];orphan=[];invalid=[];linked=set()
    findings=view['state']['workflow'].get('checks',{}).get('aerospace',{}).get('engineering',{}).get('findings',[])
    reviews=load(platform,data)['finding_reviews']
    for test in tests:
        refs=test.get('requirement_ids',test.get('requirement_id',[]));refs=refs if isinstance(refs,list) else [refs] if refs else []
        if not refs or any(str(r) not in ids for r in refs):orphan.append(test.get('id'))
        result=results.get(str(test.get('id')))
        for ref in refs:
            if str(ref) not in ids:continue
            linked.add(str(ref));source=test.get('source_ref');valid=source in view['known']
            if not valid:invalid.append({'test_id':test.get('id'),'source_ref':source})
            affected=[f for f in findings if f.get('artifact_id') in (test.get('id'),ref)]
            chains.append({'requirement_id':ref,'test_id':test.get('id'),'test_source_ref':source,'source_valid':valid,
                'execution':result,'result':result['status'] if result else 'NOT_EXECUTED',
                'findings':affected,'reviews':[r for r in reviews if r['input_digest']==view['digest'] and r['finding'] in {f['id'] for f in affected}],
                'evidence_ref':result.get('source_ref') if result else None})
    return {'schema_version':'sx-traceability-1','input_digest':view['digest'],'requirements':len(ids),'tests':len(tests),'chains':chains,
        'missing_test_links':sorted(ids-linked),'orphan_tests':orphan,'invalid_evidence_refs':invalid,
        'failed_executions':[c for c in chains if c['result']=='FAIL'],'unverified_requirements':sorted(ids-{str(c['requirement_id']) for c in chains if c['result']=='PASS'}),
        'coverage':execution['coverage'],'source_review_current':view['state']['workflow'].get('review_current') or view['state']['approved'],
        'boundary':'Linkage and supplied reviewed execution results only; structural coverage requires actual instrumented tool exports.'}

def public(platform,data):
    view=snapshot(platform,data);engine=EngineeringStore(platform.scope(data)[2]);stored=load(platform,data)
    workflow=EngineeringWorkflow(platform.scope(data)[2],view['state']['client']['revision']).load()
    rules=[]
    for rule in view['knowledge']['engineering_rules']:
        app=rule['applicability'];dal=view['knowledge']['dal'];reason='eligible for applicability review'
        if not rule['active']:reason='inactive / '+rule['status']
        elif dal['review_status']!='approved':reason='project DAL requires review'
        elif dal['value'] not in app['dal']:reason='software level not applicable'
        elif 'all' not in app['artifact_types'] and view['state']['project_detail']['activity'] not in app['artifact_types']:reason='artifact type not applicable'
        else:reason='active; execution checks source and configuration gates'
        rules.append({'rule_id':rule['rule_id'],'title':rule['title'],'status':rule['status'],'active':rule['active'],
            'severity':rule.get('severity','medium'),'applicability':app,'selection_reason':reason,'source':rule['source'],'qualification':rule.get('qualification')})
    checks=workflow.get('checks',{});aerospace=checks.get('aerospace',{}).get('engineering',{})
    standard_findings=aerospace.get('findings',[])
    general=[]
    for index,f in enumerate(checks.get('findings',[])):
        general.append({**f,'id':'WF-'+identity([index,f])[:20],'rule_id':f['check'],'severity':'medium' if f['status']=='FAIL' else 'info',
            'artifact_id':f.get('item'),'explanation':f.get('message'),'evidence':{'project_source_ref':f.get('source_ref')},'review_status':'unreviewed',
            'classification':'ai_assisted_or_human_review' if f['status']=='REVIEW_REQUIRED' else 'deterministic'})
    finding_reviews={r['finding']:r for r in stored['finding_reviews'] if r['input_digest']==view['digest']}
    findings=[{**f,'review':finding_reviews.get(f['id'])} for f in standard_findings+general]
    history=platform.engineering_assistant.history(data)
    result={'schema_version':'sx-operational-1','input_digest':view['digest'],'sources':view['state']['workflow']['sources'],
        'canonical':view['datasets'],'canonical_review_current':bool(view['state']['workflow'].get('review_current') or view['state']['approved']),
        'applicable_rules':rules,'findings':findings,'checks_current':stored.get('last_check_digest')==view['digest'],
        'traceability':traceability(platform,data),'assistant_runs':history.get('runs',[]),'events':stored['events'],
        'report_review':stored.get('report_review') if stored.get('report_review',{}).get('digest')==view['digest'] else None,
        'limitations':['Source files are immutable. Derived corrections require approval and re-check.','AI observations are reviewable proposals, not definitive compliance failures.']}
    result['report_digest']=identity({key:result[key] for key in ('input_digest','sources','canonical','applicable_rules','findings','traceability','canonical_review_current','checks_current')})
    if result['report_review'] and result['report_review'].get('report_digest')!=result['report_digest']:result['report_review']=None
    return result

def action(platform,operation,data):
    if operation in ('state','traceability'):
        with platform.lock:return public(platform,data) if operation=='state' else traceability(platform,data)
    # Native inference runs through existing asynchronous jobs and preserves their recovery.
    if operation in ('understand','correction','generate-tests'):
        prompt=data.get('prompt','')
        if not isinstance(prompt,str) or not prompt.strip():raise ValueError('Enter an evidence-scoped analysis request')
        result=platform.engineering_assistant.start({**data,'prompt':prompt,'page':'workflow','workflow_operation':operation})
        with platform.lock:event(platform,data,operation,'queued',{'job_id':result['job_id']})
        return result
    with platform.lock:
        try:
            client,project,directory=platform.scope(data)
            if operation=='import':result=platform.action('workflow-upload',data)
            elif operation=='extract':result=platform.action('workflow-extract',data)
            elif operation in ('review-canonical','apply-correction','review-correction','review-finding','review-report'):
                user=platform.reviewer_auth.require(client,project,data.get('session_token'));actor=user['username']
                if operation=='review-canonical':
                    result=platform.action('workflow-review',{**data,'reviewer':actor})
                elif operation=='review-correction':result=platform.engineering_assistant.review({**data,'reviewer':actor})
                elif operation=='apply-correction':
                    result=platform.engineering_assistant.apply({**data,'reviewer':actor})
                    platform.action('workflow-review',{**data,'reviewer':actor})
                    result=platform.action('workflow-check',{**data,'checks':data.get('checks',list(CHECKS)),
                        'policy':data.get('policy',platform.state(data)['settings']['precision'])})
                    _,path=files(platform,data);stored=load(platform,data);stored['last_check_digest']=snapshot(platform,data)['digest'];ClientStore._atomic(path,json.dumps(stored,indent=2).encode())
                elif operation=='review-finding':
                    view=public(platform,data)
                    if data.get('input_digest')!=view['input_digest']:raise ValueError('Findings changed; refresh before review')
                    if data.get('finding') not in {f['id'] for f in view['findings']}:raise ValueError('Unknown finding in selected project')
                    if data.get('decision') not in ('reviewed','needs_correction','rejected'):raise ValueError('Choose a finding review decision')
                    if not data.get('rationale','').strip():raise ValueError('Finding review needs rationale')
                    _,path=files(platform,data);stored=load(platform,data);stored['finding_reviews'].append({'finding':data['finding'],'input_digest':view['input_digest'],'reviewer':actor,'decision':data['decision'],'rationale':data['rationale'],'at':now()});ClientStore._atomic(path,json.dumps(stored,indent=2).encode());result={'status':'reviewed'}
                else:
                    view=public(platform,data)
                    if data.get('input_digest')!=view['input_digest'] or not view['canonical_review_current'] or not view['checks_current']:raise ValueError('Review current sources and re-check before approving this report')
                    _,path=files(platform,data);stored=load(platform,data);stored['report_review']={'digest':view['input_digest'],'report_digest':view['report_digest'],'reviewer':actor,'at':now()};ClientStore._atomic(path,json.dumps(stored,indent=2).encode());result={'status':'report_reviewed'}
            elif operation in ('check','recover'):
                result=platform.action('workflow-check',{**data,'checks':data.get('checks',list(CHECKS)),
                    'policy':data.get('policy',platform.state(data)['settings']['precision'])})
                _,path=files(platform,data);stored=load(platform,data);stored['last_check_digest']=snapshot(platform,data)['digest'];ClientStore._atomic(path,json.dumps(stored,indent=2).encode())
            elif operation=='export':
                view=public(platform,data)
                if not view['report_review'] or not view['checks_current']:raise ValueError('Approve the current report before export')
                result={'filename':'aerospace-verification-report.json','report':view,'boundary':'Verification-support report; no certification claim'}
            else:raise ValueError('Unknown operational verification action')
            event(platform,data,operation,'completed',{'input_digest':snapshot(platform,data)['digest']})
            return result if operation=='export' else public(platform,data)
        except Exception as exc:
            event(platform,data,operation,'failed',error=str(exc));raise
