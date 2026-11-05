import test,{after} from 'node:test'
import assert from 'node:assert/strict'
import {createServer} from 'vite'
import {createElement} from 'react'
import {renderToStaticMarkup} from 'react-dom/server'
const server=await createServer({server:{middlewareMode:true,hmr:false,watch:null},appType:'custom'})
after(()=>server.close())
const {default:Assistant}=await server.ssrLoadModule('/src/WorkspaceAssistant.tsx')
const render=model=>renderToStaticMarkup(createElement(Assistant,{client:'client1',project:'project1',page:'import',model}))
test('assistant shows project scope and configured model without claiming inference availability',()=>{
 const html=render('llama3.2:latest')
 for(const text of ['App &amp; project data only','Read-only','Configured model','llama3.2:latest','How do I use Smart Import?'])assert.ok(html.includes(text))
 assert.doesNotMatch(html,/offline fallback|Ollama connected|Inference passed/)
})
test('unassigned assistant remains usable for built-in guidance without pretending a model is assigned',()=>{
 const html=render(undefined)
 assert.match(html,/Not assigned/)
 assert.match(html,/Message SX Aerospace assistant/)
 assert.match(html,/aria-label="Send message"[^>]*disabled/)
})
