import test,{after} from 'node:test'
import assert from 'node:assert/strict'
import {createServer} from 'vite'
import {createElement} from 'react'
import {renderToStaticMarkup} from 'react-dom/server'

const server=await createServer({server:{middlewareMode:true,hmr:false,watch:null},appType:'custom'})
after(()=>server.close())
const {default:ProjectDetails}=await server.ssrLoadModule('/src/ProjectDetails.tsx')
const state={project:'stable-project-key',project_detail:{name:'project1',description:'Flight control review',activity:'LLR',process:'verification'},client:{name:'Aerospace client'},projects:[{name:'PRIVATE_OTHER_PROJECT',description:'PRIVATE_DESCRIPTION'}],documents:[{hash:'a'.repeat(64),name:'control.c'}],draft:{},runs:[],settings:{agents:{}},workflow:{sources:[{id:'a'.repeat(64),name:'control.c',format:'cpp'}],template:{format:'xlsx',reference:{name:'customer-format.xlsx'}},setup:{task:'variables',source_types:['.c','.h']}}}
const render=s=>renderToStaticMarkup(createElement(ProjectDetails,{s,go:()=>{}}))
test('dedicated page shows selected project details without other project data',()=>{
 const html=render(state)
 for(const text of ['project1','Flight control review','Aerospace client','LLR','Smart Check','Project configuration','customer-format.xlsx','Back to projects'])assert.ok(html.includes(text))
 assert.doesNotMatch(html,/PRIVATE_OTHER_PROJECT|PRIVATE_DESCRIPTION/)
})
test('only enabled workflow actions are offered and duplicate source evidence is counted once',()=>{
 const html=render(state)
 assert.match(html,/<b>Smart Check<\/b>/)
 assert.doesNotMatch(html,/<b>Smart Generate<\/b>/)
 assert.equal((html.match(/<b>control.c<\/b>/g)||[]).length,1)
 const full=render({...state,project_detail:{...state.project_detail,process:'workflow'}})
 assert.match(full,/<b>Smart Generate<\/b>/)
})
test('empty projects display missing data honestly',()=>{
 const html=render({project:'new',project_detail:{name:'New project',activity:'HLT',process:'import'},client:{name:'Client'}})
 assert.match(html,/No description yet/)
 assert.match(html,/Not recorded/)
 assert.match(html,/No source files have been imported/)
 assert.match(html,/Data review required/)
 assert.doesNotMatch(html,/<b>Smart Check<\/b>|<b>Smart Generate<\/b>/)
})
