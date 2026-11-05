import { useEffect, useState } from 'react'
import { Activity, ArrowUpRight, Bot, CheckCircle2, Send, Layers3 } from 'lucide-react'
import './AgentConsole.css'
import { FilePanel, DownloadResponse } from './AgentFiles'

type Service = { chat: string; docs: string }
type Result = { answer: string; steps: Record<string, unknown>[] }
type Entry = { prompt: string; result?: Result; error?: string }
const label = (name: string) => name.split('-').map(word => ['llr','llt','hlt','json'].includes(word) ? word.toUpperCase() : word[0].toUpperCase() + word.slice(1)).join(' ')
const group = (name: string) => name.startsWith('llt') ? 'LLT' : name.startsWith('hlt') ? 'HLT' : name.startsWith('json') || name.startsWith('output') ? 'Utilities' : 'LLR'
async function read<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, options)
  if (!response.ok) {
    const body = await response.text()
    throw new Error('Request failed (' + response.status + '): ' + body)
  }
  return response.json()
}
export default function AgentConsole() {
  const [services, setServices] = useState<Record<string, Service>>({})
  const [selected, setSelected] = useState('')
  const [health, setHealth] = useState<Record<string, string>>({})
  const [error, setError] = useState('')
  const [query, setQuery] = useState('')
  const [drafts, setDrafts] = useState<Record<string, string>>({})
  const [entries, setEntries] = useState<Record<string, Entry[]>>({})
  const [pending, setPending] = useState<Record<string, boolean>>({})
  const [chosen, setChosen] = useState<Record<string, string[]>>({})
  async function refresh() {
    setError('')
    try {
      const data = await read<Record<string, Service>>('/services')
      setServices(data)
      setSelected(current => current && data[current] ? current : Object.keys(data)[0] || '')
      const checks = await Promise.all(Object.keys(data).map(async name => {
        try { const h = await read<{model:string}>('/agents/' + name + '/health'); return [name, h.model] }
        catch { return [name, 'Unavailable'] }
      }))
      setHealth(Object.fromEntries(checks))
    } catch (e) { setError(e instanceof Error ? e.message : String(e)) }
  }
  useEffect(() => { void refresh() }, [])
  async function submit() {
    const name = selected
    const request = (drafts[name] || '').trim()
    const attachments = chosen[name] || []
    const prompt = request + (attachments.length ? '\n\nRead these selected documents using read_document before answering (paths relative to your documents directory):\n' + attachments.map(file => JSON.stringify(file)).join('\n') : '')
    if (!request || pending[name]) return
    if (prompt.length > 10000) { setError('Request plus filenames exceeds 10,000 characters. Shorten your request.'); return }
    setPending(p => ({...p, [name]: true}))
    setDrafts(d => ({...d, [name]: ''}))
    setEntries(all => ({...all, [name]: [...(all[name] || []), {prompt}]}))
    try {
      const result = await read<Result>(services[name].chat, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({message:prompt})})
      setEntries(all => ({...all, [name]: (all[name] || []).map((entry, i, list) => i === list.length - 1 ? {...entry, result} : entry)}))
    } catch (e) {
      setEntries(all => ({...all, [name]: (all[name] || []).map((entry, i, list) => i === list.length - 1 ? {...entry, error:e instanceof Error ? e.message : String(e)} : entry)}))
    } finally { setPending(p => ({...p, [name]:false})) }
  }
  return <div className="console">
    <aside className="sidebar">
      <div className="brand"><Layers3 size={30}/><div>ENGINEERING<span>Multi-agent workspace</span></div></div>
      <div className="nav-title">AGENT DIRECTORY <b>{Object.keys(services).length}</b></div>
      <input aria-label="Search agents" className="search" placeholder="Search agents…" value={query} onChange={e => setQuery(e.target.value)}/>
      <nav aria-label="Backend agents">{['LLR','LLT','HLT','Utilities'].map(category => <section key={category}><h2>{category}</h2>{Object.keys(services).filter(name => group(name) === category && label(name).toLowerCase().includes(query.toLowerCase())).map(name => <button key={name} aria-current={selected === name ? 'page' : undefined} className={selected === name ? 'agent active' : 'agent'} onClick={() => setSelected(name)}><Bot size={17}/><span>{label(name)}</span><i className={health[name] && health[name] !== 'Unavailable' ? 'dot ready' : 'dot'}/></button>)}</section>)}</nav>
      <div className="sidebar-footer"><Activity size={15}/> Local Ollama · Private workspace</div>
    </aside>
    <main>
      <header><span>Workspace / Agent console</span><div><a href="/docs" target="_blank" rel="noreferrer">API docs <ArrowUpRight size={14}/></a><button onClick={() => void refresh()}>Refresh status</button></div></header>
      <div className="workspace">
        <div className="eyebrow">ENGINEERING OPERATIONS</div>
        <h1>Your specialist agents.<br/><span>One connected workspace.</span></h1>
        <p className="intro">Select a backend service, provide your request and inspect its response and tool activity.</p>
        <div className="stats"><div><Layers3/><span><strong>{Object.keys(services).length}</strong> Backend services</span></div><div><CheckCircle2/><span><strong>{Object.values(health).filter(v => v !== 'Unavailable').length} ready</strong> API health</span></div><div><Bot/><span><strong>{health[selected] || 'Checking…'}</strong> Configured model</span></div></div>
        {error && <p role="alert" className="error">{error}</p>}
        {selected && <section className="work-panel">
          <div className="panel-heading"><div><span className="badge">{group(selected)}</span><h2>{label(selected)}</h2></div><a href={services[selected].docs} target="_blank" rel="noreferrer">Service docs <ArrowUpRight size={15}/></a></div>
          <p className="notice">Each request is independent. Include the context you need. API health does not confirm model inference. Outputs require engineering review.</p>
          <FilePanel key={selected} agent={selected} chosen={chosen[selected] || []} onChoose={files => setChosen(current => ({...current, [selected]:files}))}/><div className="conversation" aria-live="polite">
            {!(entries[selected] || []).length && <div className="empty"><Bot size={38}/><h3>Start a request</h3><p>Paste requirements, test evidence or text to process.</p><button onClick={() => setDrafts(d => ({...d, [selected]:'List available documents using the list_documents tool.'}))}>List this agent’s documents</button></div>}
            {(entries[selected] || []).map((entry, index) => <article key={index}><div className="prompt"><small>YOUR REQUEST</small><pre>{entry.prompt}</pre></div>{entry.result && <div className="answer"><small>AGENT RESPONSE</small><pre>{entry.result.answer}</pre><DownloadResponse answer={entry.result.answer} agent={selected}/>{entry.result.steps.length > 0 && <details><summary>Tool activity ({entry.result.steps.length})</summary><pre>{JSON.stringify(entry.result.steps, null, 2)}</pre></details>}</div>}{entry.error && <p role="alert" className="error">{entry.error}</p>}</article>)}
            {pending[selected] && <p className="working" role="status">Agent is working with the local model…</p>}
          </div>
          <form onSubmit={e => {e.preventDefault(); void submit()}}>
            <label htmlFor="request">Request for {label(selected)}</label>
            <textarea id="request" maxLength={10000} rows={4} placeholder="Describe the task and include relevant context…" value={drafts[selected] || ''} onChange={e => setDrafts(d => ({...d, [selected]: e.target.value}))}/>
            <div className="composer-footer"><span>{(drafts[selected] || '').length}/10,000 characters</span><button type="submit" disabled={pending[selected] || !(drafts[selected] || '').trim()}><Send size={16}/>{pending[selected] ? 'Running…' : 'Send request'}</button></div>
          </form>
        </section>}
      </div>
    </main>
  </div>
}

