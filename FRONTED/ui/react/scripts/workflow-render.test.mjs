import test, {after} from 'node:test'
import assert from 'node:assert/strict'
import {createServer} from 'vite'
import {createElement} from 'react'
import {renderToStaticMarkup} from 'react-dom/server'

const server=await createServer({server:{middlewareMode:true,hmr:false,watch:null},appType:'custom'})
after(()=>server.close())
const {default:Workflow}=await server.ssrLoadModule('/src/EngineeringWorkflow.tsx')
const source={id:'a'.repeat(64),name:'control.c',format:'cpp',unsupported:[]}
const data={variables:[{name:'speed',type:'float',value:'0.1',scope:'global',source:'control.c',source_ref:source.id}],requirements:[],parameters:[],samples:[],test_cases:[],tables:[],text:[]}
const state={project_detail:{activity:'LLR',process:'workflow'},workflow:{sources:[source],plan:[],template:{format:'xlsx',title:'Evidence',sheets:[{name:'Variables',dataset:'variables',columns:['name','value']}]},extraction:{datasets:data,limitations:['Lexical extraction requires engineering review.']},review_current:true,review:{reviewer:'Engineer'},checks:{findings:[{check:'range',status:'INSUFFICIENT_INFORMATION',message:'No observed samples'}],test_cases:[]}}}
function render(tab,s=state){return renderToStaticMarkup(createElement(Workflow,{s,tab,busy:false,run:async()=>true,go:()=>{}}))}

test('each engineering interface renders its own controls',()=>{
 assert.match(render('import'),/Import selected files/)
 assert.match(render('import'),/Engineering activity/)
 assert.match(render('import'),/Required source file types/)
 assert.match(render('import'),/Expected output/)
 assert.match(render('import'),/Import output reference/)
 assert.match(render('extract'),/Approve extracted data/)
 assert.match(render('check'),/Run selected checks/)
 assert.match(render('generation'),/Generate draft artifact/)
 assert.doesNotMatch(render('import'),/1 Upload2 Understand/)
})
test('reviewed records and evidence gaps remain visible',()=>{
 assert.match(render('extract'),/control.c/)
 assert.match(render('extract'),/speed/)
 assert.match(render('check'),/No observed samples/)
 assert.match(render('generation'),/Column fill templates JSON/)
})
test('restricted projects retain navigation and explain the generation gate',()=>{
 const restricted={...state,project_detail:{activity:'HLT',process:'verification'}}
 const html=render('generation',restricted)
 assert.match(html,/Select Complete Workflow or Test Generation/)
 assert.match(html,/disabled=""[^>]*><svg[^]*?Generate draft artifact/)
})
test('empty projects render all four interfaces without exceptions',()=>{
 const empty={project_detail:{activity:'LLR',process:'workflow'},workflow:{sources:[],plan:[],template:state.workflow.template}}
 for(const tab of ['import','extract','check','generation'])assert.match(render(tab,empty),/Engineering Workflow/)
})


test('prompt and manual configuration modes are available above the workflow',()=>{
 const html=render('import')
 assert.match(html,/By prompt/)
 assert.match(html,/Manual/)
 const promptState={...state,workflow:{...state.workflow,prompting:{mode:'prompt',prompt:'Create an Excel variable inventory',status:'ready',proposal:{summary:'Variables inventory',setup:{activity:'LLR',task:'variables',source_types:['.c','.h']},plan:[],checks:['precision'],policy:{mode:'decimal_places',digits:6},template:state.workflow.template,limitations:[]}}}}
 const proposal=render('import',promptState)
 assert.match(proposal,/Workflow configuration prompt/)
 assert.match(proposal,/Propose configuration/)
 assert.match(proposal,/Apply configuration to interfaces/)
 assert.match(proposal,/Variables inventory/)
})
test('backend plans without optional field lists remain readable',()=>{
 const s=structuredClone(state);s.workflow.plan=[{source_ref:source.id,dataset:'variables'}]
 assert.match(render('extract',s),/control.c/)
})

test('output reference picker accepts every file type and explains guidance mode',()=>{
 const html=render('import')
 assert.match(html,/Upload any reference file/)
 assert.doesNotMatch(html,/accept="\.xlsx,\.docx"/)
 const s=structuredClone(state);s.workflow.template.reference={name:'design.png',mode:'guidance',format:'xlsx',notes:['Configure the output layout manually']}
 const output=render('generation',s)
 assert.doesNotMatch(output,/select disabled/)
 assert.match(render('import',s),/Configure the output layout manually/)
})
