import test,{after} from 'node:test'
import assert from 'node:assert/strict'
import {createServer} from 'vite'
import {createElement} from 'react'
import {renderToStaticMarkup} from 'react-dom/server'
const server=await createServer({server:{middlewareMode:true,hmr:false,watch:null},appType:'custom'})
after(()=>server.close())
const {default:Workspace,schemaFromFields}=await server.ssrLoadModule('/src/PromptWorkspace.tsx')
const s={client:{id:'qa'},project:'qa',documents:[]}
test('translation exposes input instructions and expected output without login',()=>{
 const html=renderToStaticMarkup(createElement(Workspace,{s}))
 for(const text of ['Qwen JSON Translator','Upload source files','Instructions','JSON Structure','Review &amp; Download'])assert.ok(html.includes(text),text)
 assert.ok(!html.includes('Sign in reviewer'))
})
test('check and generation remain distinct exploratory flows',()=>{
 const check=renderToStaticMarkup(createElement(Workspace,{s,mode:'check'}))
 assert.match(check,/Temporary rules/);assert.match(check,/exploratory AI observations/)
 const tests=renderToStaticMarkup(createElement(Workspace,{s,mode:'tests'}))
 for(const level of ['HLT','LLT','Integration'])assert.ok(tests.includes(level))
})
test('history provides source requirement links and downloads heading',()=>{
 const html=renderToStaticMarkup(createElement(Workspace,{s,mode:'history'}))
 assert.match(html,/Results &amp; Downloads/);assert.match(html,/Source &amp; Requirement Links/)
})
test('visual field builder supports nesting and rejects unsafe or conflicting paths',()=>{
 const schema=schemaFromFields([{name:'record.identifier',type:'string'},{name:'record.active',type:'boolean'}])
 assert.equal(schema.properties.record.properties.identifier.type,'string')
 assert.throws(()=>schemaFromFields([{name:'__proto__.x',type:'string'}]))
 assert.throws(()=>schemaFromFields([{name:'a',type:'string'},{name:'a.b',type:'string'}]))
})
test('stored files expose edit and delete controls with escaped names',()=>{
 const html=renderToStaticMarkup(createElement(Workspace,{s:{...s,documents:[{hash:'abc',name:'<script>source</script>.txt'}]}}))
 assert.match(html,/Stored project files/)
 assert.match(html,/>Modifier<\/button>/)
 assert.match(html,/>Supprimer<\/button>/)
 assert.match(html,/&lt;script&gt;source&lt;\/script&gt;/)
 assert.doesNotMatch(html,/<script>source<\/script>/)
})


test('translator offers schema choices in the guided structure step',async()=>{
 const {default:Translator}=await server.ssrLoadModule('/src/JsonTranslator.tsx')
 const html=renderToStaticMarkup(createElement(Translator,{s,initialStep:3}))
 for(const label of ['Automatic Qwen-designed JSON','SX Canonical JSON','Custom JSON Schema'])assert.ok(html.includes(label))
 assert.ok(!html.includes('prompt-grid'))
})


test('table preview preserves big integers and decimal tokens without JS float conversion',async()=>{
 const {exactPreview}=await server.ssrLoadModule('/src/JsonTranslator.tsx')
 const output=exactPreview('{"gain":0.123456789012345678901234567890,"serial":123456789012345678901,"text":"1.2300 ms"}')
 assert.equal(output.gain,'0.123456789012345678901234567890')
 assert.equal(output.serial,'123456789012345678901')
 assert.equal(output.text,'1.2300 ms')
})
