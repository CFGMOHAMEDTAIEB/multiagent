import test,{after} from 'node:test'
import assert from 'node:assert/strict'
import {createServer} from 'vite'
import {createElement} from 'react'
import {renderToStaticMarkup} from 'react-dom/server'
const server=await createServer({server:{middlewareMode:true,hmr:false,watch:null},appType:'custom'})
after(()=>server.close())
const {default:Standards,standardsTabs}=await server.ssrLoadModule('/src/AerospaceStandards.tsx')
const s={client:{id:'selected-client'},project:'selected-project',documents:[],workflow:{sources:[]}}
const k={documents:[],rules:[],objectives:[],evidence_mappings:[],history:[],dal:{value:null,review_status:'unconfigured'},topics:['requirements','verification'],categories:['deterministic','engineering_judgment','additional_evidence','human_review'],admin_configured:false,retrieval_method:'local LSA + keyword'}
const render=(tab,state=k)=>renderToStaticMarkup(createElement(Standards,{s,initialTab:tab,initialKnowledge:state}))
test('all seven standards workflows expose honest empty states',()=>{
 for(const tab of standardsTabs){const html=render(tab);assert.match(html,/Aerospace Standards/);assert.match(html,/Qwen only/);assert.match(html,/Review details/);assert.doesNotMatch(html,/Authenticated reviewer|Sign in reviewer|Create reviewer account|Administrator token|type="password"/);assert.ok(!html.includes('Certification approved'))}
 assert.match(render('Knowledge Base'),/No standards source uploaded in this project/)
 assert.match(render('DO-178C Objectives'),/No source-backed objective proposals/)
 assert.match(render('DAL Configuration'),/unconfigured/)
 assert.match(render('Evidence Mapping'),/Run approved Aerospace Smart Check/)
})
test('proposed rules show provenance and cannot approve without authorization and applicability',()=>{
 const rule={id:'ASR-fixture',version:1,active:false,review_status:'proposed',objective:'<script>source data</script>',source_quote:'Exact source text',source:{document:'doc-hash',version:'revision-1',page:16,section:'Planning',table:'p16-table1'},dal:[],testing_level:'all',category:'human_review',confidence:.5,applicability:'Unknown',required_evidence:['reviewed source'],check_type:'manual',proposed_logic:'Engineering judgment',history:[]}
 const html=render('Rule Review',{...k,rules:[rule]})
 assert.match(html,/proposed \/ inactive/);assert.match(html,/revision-1/);assert.match(html,/p\. 16/)
 assert.match(html,/&lt;script&gt;source data&lt;\/script&gt;/);assert.doesNotMatch(html,/<script>source data/)
 assert.match(html,/<button[^>]+disabled=""[^>]*>.*?approve/s)
})
