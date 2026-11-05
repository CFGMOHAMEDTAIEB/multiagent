import test,{after} from 'node:test'
import assert from 'node:assert/strict'
import {createServer} from 'vite'
import {createElement} from 'react'
import {renderToStaticMarkup} from 'react-dom/server'
const server=await createServer({server:{middlewareMode:true,hmr:false,watch:null},appType:'custom'})
after(()=>server.close())
const {default:Studio,standardsTabs}=await server.ssrLoadModule('/src/AerospaceStandards.tsx')
const {default:Operations}=await server.ssrLoadModule('/src/EngineeringRuleOperations.tsx')
const s={client:{id:'qa-client'},project:'qa-project',documents:[],workflow:{sources:[]}}
const rule={rule_id:'SX-QA-001',title:'<script>untrusted</script>',version:1,status:'approved',active:false,classification:'deterministic',applicability:{dal:['A'],artifact_types:['LLT']},unit_report:{passed:true}}
const knowledge={documents:[],rules:[],dal:{value:null},engineering:{engineering_rules:[rule]}}
test('nine studio workflows and approval/activation separation',()=>{
 assert.equal(standardsTabs.length,9)
 for(const tab of standardsTabs){const html=renderToStaticMarkup(createElement(Studio,{s,initialKnowledge:knowledge,initialTab:tab}));assert.doesNotMatch(html,/>Activate approved rule</)}
 const studio=renderToStaticMarkup(createElement(Studio,{s,initialKnowledge:knowledge,initialTab:'Rule Review'}))
 assert.match(studio,/&lt;script&gt;untrusted&lt;\/script&gt;/)
 const ops=renderToStaticMarkup(createElement(Operations,{s,initialEngineering:knowledge.engineering}))
 assert.match(ops,/Activate approved rule/);assert.match(ops,/disabled=""/)
})
test('table empty state does not fabricate extracted cells',()=>{
 const html=renderToStaticMarkup(createElement(Studio,{s,initialKnowledge:knowledge,initialTab:'Table Extraction'}))
 assert.match(html,/No table contents are inferred from captions/)
 assert.doesNotMatch(html,/aria-label="Cell /)
})
