import test,{after} from 'node:test'
import assert from 'node:assert/strict'
import {createServer} from 'vite'
import {createElement} from 'react'
import {renderToStaticMarkup} from 'react-dom/server'
const server=await createServer({server:{middlewareMode:true,hmr:false,watch:null},appType:'custom'})
after(()=>server.close())
const {AssistantResult,default:Assistant}=await server.ssrLoadModule('/src/WorkspaceAssistant.tsx')
const base={job_id:'fixture-run',status:'waiting_for_review',current:true,state:{input_version:'abc123',plan:{intent:'traceability_analysis'},timeline:[{name:'orchestrator',kind:'agent',status:'completed',model:'llama3.2:latest'},{name:'analyze_traceability',kind:'tool',status:'completed'}],artifact:{requirements:2,tests:1,link_coverage:.5,missing_links:['REQ-2'],orphan_tests:[],missing_expected_results:[]},citations:[{id:'row1',name:'control.c',version:'hash123',location:{line:1}}]}}
const render=run=>renderToStaticMarkup(createElement(AssistantResult,{run,onReview:()=>{},onRetry:()=>{},onApply:()=>{},exportUrl:'/api/assistant-export'}))
test('agentic result exposes actual timeline, source locations and operational review boundary',()=>{
 const html=render(base)
 for(const text of ['orchestrator','llama3.2:latest','analyze_traceability','50%','REQ-2','control.c','line','identity is not authenticated','Chat messages cannot approve'])assert.ok(html.includes(text),text)
 assert.ok(!html.includes('Export reviewed JSON'))
})
test('stale artifacts and incomplete candidates cannot be approved',()=>{
 const stale=render({...base,current:false});assert.match(stale,/disabled=""[^>]*>.*?Approve/)
 const incomplete=render({...base,state:{...base.state,artifact:{cases:[],incomplete:true}}});assert.match(incomplete,/Complete expected results and steps/)
})
test('generation preview explicitly labels execution and uncertainty',()=>{
 const html=render({...base,state:{...base.state,artifact:{cases:[{id:'LLT-1',level:'LLT',objective:'Check limit',requirement_ids:['REQ-1'],preconditions:[],input_data:['37'],steps:['Observe'],expected_results:[]}]}}})
 assert.match(html,/Not executed/);assert.match(html,/Unavailable/);assert.match(html,/REQ-1/)
})
test('contextual actions require source and review prerequisites',()=>{
 const html=renderToStaticMarkup(createElement(Assistant,{client:'c',project:'FCC',page:'check',capabilities:{reviewed:true,canCheck:true,canGenerate:false,hasRequirements:true}}))
 assert.match(html,/Run Smart Check/);assert.match(html,/Assess requirements/);assert.ok(!html.includes('Prepare test candidates'))
 const empty=renderToStaticMarkup(createElement(Assistant,{client:'c',project:'FCC',page:'check'}));assert.ok(!empty.includes('Run Smart Check'))
})
