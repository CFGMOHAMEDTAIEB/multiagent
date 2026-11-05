"""Agent Studio extends the existing client/project shell."""
import json
from agents.universal import OllamaAgents, ROLES
from smartx.universal import UniversalStore, new_run, execute, approve, reject, recover, export

def render_studio(st, store, client, project, sources):
    workspace=UniversalStore(store,client['id'],project)
    key=f"universal-{client['id']}-{project}"
    st.header('AI Agent Studio')
    st.caption('Source → adapters → understanding → canonical JSON → rules → verification → proposals → validation → human review → export')
    endpoint=st.text_input('Ollama endpoint', 'http://localhost:11434', key=key+'endpoint')
    service=OllamaAgents(endpoint)
    configuration=workspace.settings()
    tabs=st.tabs(['Connection & agents','Client & project configuration','Workflow & review'])
    with tabs[0]:
        if st.button('Discover installed models',key=key+'discover'):
            try:
                st.session_state[key+'models']=[m['name'] for m in service.discover()]
                st.session_state[key+'connected']=True
                st.session_state[key+'discovered_endpoint']=endpoint
                st.success('Ollama connected. Models retrieved from /api/tags.')
            except Exception as exc: st.error(f'Connection failed: {type(exc).__name__}. Check endpoint and Ollama service.')
        models=st.session_state.get(key+'models',[]) if st.session_state.get(key+'discovered_endpoint')==endpoint else []
        if st.session_state.get(key+'connected') and st.session_state.get(key+'discovered_endpoint')==endpoint and not models:
            st.info('Ollama is connected, but no local models are available.')
        runs_for_status=workspace.runs()
        logs=[entry for run in runs_for_status for entry in run.get('logs',[])]
        for row_start in range(0,len(ROLES),3):
            for column, agent_role in zip(st.columns(3),ROLES[row_start:row_start+3]):
                with column, st.container(border=True):
                    assignment=configuration['agents'][agent_role]['model']
                    st.markdown('**'+agent_role.replace('_',' ').title()+'**')
                    st.caption('Responsibility: '+agent_role.replace('_',' '))
                    st.write('Model: '+(assignment or 'Unassigned'))
                    st.caption('Installed' if assignment and assignment in models else 'Availability not verified')
                    previous=[entry for entry in logs if entry.get('agent')==agent_role]
                    st.caption('Last execution: '+(previous[-1]['status'] if previous else 'Never run'))
                    if st.button('Configure agent',key=key+'open-'+agent_role):
                        st.session_state[key+'role']=agent_role
        role=st.selectbox('Independent agent', ROLES, key=key+'role')
        agent=configuration['agents'][role]
        with st.form(key+'agent'+role):
            detail=st.tabs(['General','Model Configuration','System Prompt','JSON Schema','Execution Settings','Logs & History'])
            with detail[0]:
                st.write(role.replace('_',' ').title())
                st.caption('Independent agent configuration. Model changes are validated against the actual Ollama service before saving.')
            with detail[1]:
                if agent['model'] and agent['model'] not in models:
                    st.warning('Saved assignment: '+agent['model']+'. Discover installed models before changing this assignment.')
                model=st.selectbox('Installed completion model', ['']+models, index=(['']+models).index(agent['model']) if agent['model'] in models else 0)
            with detail[2]:
                prompt=st.text_area('System instructions',agent['system_prompt'],height=220)
            with detail[3]:
                schema=st.text_area('Structured output JSON Schema',json.dumps(agent['schema'],indent=2),height=220)
            with detail[4]:
                temperature=st.number_input('Temperature',0.0,2.0,float(agent['temperature']))
                timeout=st.number_input('Timeout (seconds)',1,600,int(agent['timeout']))
                retries=st.number_input('Retries',0,3,int(agent['retries']))
            with detail[5]:
                st.dataframe([entry for entry in logs if entry.get('agent')==role],width='stretch')
            if st.form_submit_button('Validate model & save agent'):
                try:
                    service.inspect(model)
                    configuration['agents'][role]={'model':model,'system_prompt':prompt,'temperature':temperature,'timeout':timeout,'retries':retries,'schema':json.loads(schema)}
                    workspace.save_settings(configuration,project=True)
                    st.success('Assignment validated and saved for this project.')
                except Exception as exc: st.error(str(exc))
        st.caption('Each role receives prior validated handoffs. Outputs remain proposals; documents cannot grant tools or execute code.')
    with tabs[1]:
        st.info('Precedence: platform defaults → client settings → project overrides. Lists replace earlier lists. Existing Client configuration still controls import mappings and writing conventions.')
        scope=st.radio('Save scope',['Project overrides','Client defaults'],key=key+'scope')
        raw=st.text_area('Versioned configuration JSON',json.dumps(configuration,indent=2),height=350,key=key+'config')
        if st.button('Validate & save configuration',key=key+'save'):
            try:
                workspace.save_settings(json.loads(raw),project=scope=='Project overrides'); st.success('Configuration saved.')
            except Exception as exc: st.error(str(exc))
        st.caption('Only JSON and CSV output adapters are currently enabled. Standard rule packs require supplied documented rule definitions; no certification conclusion is generated.')
    with tabs[2]:
        if st.button('Create canonical run',disabled=not sources,key=key+'new'):
            try:
                run=new_run(sources,workspace.settings(),store.context(client['id'],project)); workspace.save(run)
                st.session_state[key+'selected']=run['id']
            except Exception as exc: st.error(str(exc))
        runs=workspace.runs()
        if not runs:
            st.info('Upload sources in the sidebar, then create a run.'); return
        ids=[r['id'] for r in runs]
        selected=st.selectbox('Persisted run',ids,index=ids.index(st.session_state.get(key+'selected')) if st.session_state.get(key+'selected') in ids else len(ids)-1,key=key+'run')
        run=next(r for r in runs if r['id']==selected)
        st.metric('Workflow status',run['status'])
        if run['status'] in ('failed','rejected') and st.button('Restart with current saved settings',key=key+'recover'):
            recover(run,workspace.settings()); workspace.save(run); st.rerun()
        if st.button('Run / resume agents',disabled=run['status'] not in ('ready','failed'),key=key+'execute'):
            with st.status('Running independent agents. Each response is validated before handoff.',expanded=True):
                execute(run,service,checkpoint=workspace.save); workspace.save(run)
            st.rerun()
        if run.get('error') and run['status']=='failed': st.error(run['error'])
        st.dataframe([{k:v for k,v in entry.items() if k!='result'} for entry in run['logs']],width='stretch')
        with st.expander('Canonical JSON and source lineage'): st.json(run['cir'])
        with st.expander('Agent messages and proposed corrections / tests'): st.json(run['messages'])
        with st.expander('Numeric formatting proposals'): st.json(run.get('numeric_format_proposals',[]))
        with st.expander('Rule findings and audit evidence'): st.json({'findings':run['findings'],'audit':run['audit']})
        reviewer=st.text_input('Reviewer name',key=key+'reviewer')
        reason=st.text_input('Reason / requested correction',key=key+'reason')
        if st.button('Reject and request changes',disabled=run['status']!='human_review',key=key+'reject'):
            try: reject(run,reviewer,reason); workspace.save(run); st.rerun()
            except Exception as exc: st.error(str(exc))
        if st.button('Approve reviewed artifacts',disabled=run['status']!='human_review',key=key+'approve'):
            try: approve(run,reviewer); workspace.save(run); st.rerun()
            except Exception as exc: st.error(str(exc))
        if run['status']=='approved':
            for kind in run['configuration']['export_formats']:
                st.download_button('Export '+kind.upper(),export(run,kind),f'sx-{run["id"]}.{kind}',key=key+kind)
