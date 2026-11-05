import test,{after} from 'node:test'
import assert from 'node:assert/strict'
import {createServer} from 'vite'
import {createElement} from 'react'
import {renderToStaticMarkup} from 'react-dom/server'
const server=await createServer({server:{middlewareMode:true,hmr:false,watch:null},appType:'custom'})
after(()=>server.close())
const {default:Workspace,verificationTabs}=await server.ssrLoadModule('/src/OperationalVerification.tsx')
const {default:Auth}=await server.ssrLoadModule('/src/ReviewerSession.tsx')
const {default:Qualification}=await server.ssrLoadModule('/src/RuleQualification.tsx')
const s={client:{id:'qa',name:'Synthetic client'},project:'Synthetic project'}
const view={sources:[],canonical:{},canonical_review_current:false,applicable_rules:[],findings:[],traceability:{coverage:{mcdc:{status:'INSUFFICIENT_EVIDENCE'}}},assistant_runs:[],events:[],checks_current:false,report_review:null}
const render=(tab,data=view)=>renderToStaticMarkup(createElement(Workspace,{s,go(){},initialState:data,initialTab:tab}))
test('seven focused operational tabs render honest empty states',()=>{
 assert.equal(verificationTabs.length,7)
 for(const tab of verificationTabs){const html=render(tab);assert.match(html,/Verification Workspace/);assert.doesNotMatch(html,/Authenticated reviewer|Sign in reviewer|Create reviewer account|type="password"/)}
 assert.match(render('Applicable Rules'),/No DO-178C objectives are inferred/)
 assert.match(render('Traceability'),/INSUFFICIENT_EVIDENCE/)
 assert.match(render('Export'),/disabled=""[^>]*>Export reviewed report/)
})
test('finding source content is escaped and unauthenticated review remains disabled',()=>{
 const html=render('Findings',{...view,findings:[{id:'F1',rule_id:'SX-QA',status:'FAIL',severity:'high',artifact_id:'R1',explanation:'<script>untrusted</script>'}]})
 assert.match(html,/&lt;script&gt;untrusted&lt;\/script&gt;/)
 assert.doesNotMatch(html,/<script>untrusted/)
 assert.match(html,/disabled=""[^>]*>Record finding review/)
})
test('reviewer forms are absent and qualification retains its server authorization boundary',()=>{
 const auth=renderToStaticMarkup(createElement(Auth,{s}))
 assert.equal(auth,'')
 const qualification=renderToStaticMarkup(createElement(Qualification,{s,rule:{status:'under_review',rule_id:'SX-QA',version:1},request(){},perform(){},admin:{}}))
 assert.match(qualification,/positive, negative, boundary, missing_data, malformed_input, applicability, client_override/)
 assert.match(qualification,/disabled=""[^>]*>Run qualification suite/)
})
