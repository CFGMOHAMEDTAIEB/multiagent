import test,{after} from 'node:test'
import assert from 'node:assert/strict'
import {createServer} from 'vite'
import {createElement} from 'react'
import {renderToStaticMarkup} from 'react-dom/server'

const server=await createServer({server:{middlewareMode:true,hmr:false,watch:null},appType:'custom'})
after(()=>server.close())
const {default:Studio,balancedModels,modelFamily}=await server.ssrLoadModule('/src/AgentStudio.tsx')
const roles=['file_understanding','json_transformation','client_configuration','standards_retrieval','verification','test_generation','traceability','reporting','orchestrator']
const models=['qwen3:4b-instruct','qwen2.5-coder:latest']
const s={roles,settings:{agents:Object.fromEntries(roles.map(role=>[role,{name:role.replaceAll('_',' '),model:models[1],system_prompt:'Preserve evidence',schema:{type:'object'},temperature:0,timeout:120,retries:1}]))},model_tests:{}}
const render=(state=s,available=models)=>renderToStaticMarkup(createElement(Studio,{s:state,models:available,busy:false,run:async()=>true,refresh:async()=>{}}))
test('studio removes retired sections and presents installed model cards',()=>{
 const html=render()
 for(const label of ['General','Execution Settings','Logs'])assert.doesNotMatch(html,new RegExp('>'+label+'<'))
 for(const label of ['Models','Instructions','Output Schema','Balance installed models','qwen3:4b-instruct','qwen2.5-coder:latest'])assert.ok(html.includes(label))
 assert.match(html,/<img[^>]+alt="Technical aircraft illustration/)
})
test('balancing uses installed model families without replacing prompts or execution settings',()=>{
 const assignments=balancedModels(roles,models)
 assert.equal(assignments.verification.model,models[0])
 assert.equal(assignments.test_generation.model,models[1])
 assert.equal(assignments.reporting.model,models[1])
 assert.equal(assignments.orchestrator.model,models[0])
 assert.ok(Object.values(assignments).every(patch=>Object.keys(patch).join()==='model'))
 assert.equal(new Set(Object.values(assignments).map(x=>x.model)).size,2)
 assert.ok(Object.values(balancedModels(roles,[models[0]])).every(x=>x.model===models[0]));assert.throws(()=>balancedModels(roles,[]),/No verified installed Qwen/)
})
test('unavailable models are not presented as verified inference',()=>{
 assert.match(render(s,[]),/No installed models/)
 assert.match(render(),/Inference not yet verified/)
 assert.equal(modelFamily('qwen3:4b-instruct'),'Qwen')
})
