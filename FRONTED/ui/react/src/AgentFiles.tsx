import { useEffect, useState } from 'react'

export type AgentFile = { name: string; size: number }
export function FilePanel({agent, chosen, onChoose}: {agent:string; chosen:string[]; onChoose:(files:string[])=>void}) {
  const [files, setFiles] = useState<AgentFile[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  async function refresh() {
    const response = await fetch('/files/' + agent)
    if (!response.ok) throw new Error('Could not load documents')
    setFiles(await response.json())
  }
  useEffect(() => {
    let active = true
    setFiles([]); setError('')
    fetch('/files/' + agent).then(async response => {
      if (!response.ok) throw new Error('Could not load documents')
      const data = await response.json()
      if (active) setFiles(data)
    }).catch(e => { if (active) setError(String(e)) })
    return () => { active = false }
  }, [agent])
  async function upload(input: HTMLInputElement) {
    const uploads = Array.from(input.files || [])
    setBusy(true); setError('')
    const added: string[] = []
    try {
      for (const file of uploads) {
        if (file.size > 1000000) throw new Error(file.name + ': exceeds 1 MB')
        const response = await fetch('/files/' + agent + '?filename=' + encodeURIComponent(file.name), {method:'POST', headers:{'Content-Type':'application/octet-stream'}, body:file})
        if (!response.ok) {
          const body = await response.json()
          throw new Error(file.name + ': ' + body.detail)
        }
        added.push((await response.json()).name)
      }
    } catch (e) { setError(e instanceof Error ? e.message : String(e)) }
    finally {
      onChoose([...new Set([...chosen, ...added])].slice(0, 3))
      try { await refresh() } catch (e) { setError(String(e)) }
      setBusy(false); input.value = ''
    }
  }
  return <section className="file-panel">
    <h3>Agent documents</h3>
    <p>Upload TXT, Markdown, JSON or CSV in UTF-8 (1 MB each; simple filenames up to 100 characters). Files stay with this agent. Select up to 3 for your next request.</p>
    <label className="upload-label">Upload files<input aria-label="Upload agent files" type="file" multiple accept=".txt,.md,.json,.csv" disabled={busy} onChange={e => void upload(e.currentTarget)}/></label>
    {busy && <p role="status">Uploading…</p>}
    {error && <p role="alert" className="error">{error}</p>}
    {files.length === 0 && <p>No documents uploaded yet.</p>}
    <ul>{files.map(file => <li key={file.name}><label><input type="checkbox" checked={chosen.includes(file.name)} disabled={busy || (!chosen.includes(file.name) && chosen.length >= 3)} onChange={e => onChoose(e.target.checked ? [...chosen, file.name] : chosen.filter(name => name !== file.name))}/><span>{file.name}</span></label><span>{Math.ceil(file.size/1024)} KB</span><a href={'/files/' + agent + '/' + encodeURIComponent(file.name)} download>Download</a></li>)}</ul>
    <p>Document tools read the first 16,000 characters of each file. PDF, Word, Excel and images are not supported yet.</p>
  </section>
}
export function DownloadResponse({answer, agent}: {answer:string; agent:string}) {
  const [format, setFormat] = useState('md')
  function download() {
    const content = format === 'json' ? JSON.stringify({agent, answer}, null, 2) : answer
    const url = URL.createObjectURL(new Blob([content], {type:format === 'json' ? 'application/json' : 'text/plain;charset=utf-8'}))
    const anchor = document.createElement('a')
    anchor.href = url; anchor.download = agent + '-response.' + format
    anchor.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  }
  return <div className="download-response"><label>Download format<select value={format} onChange={e => setFormat(e.target.value)}><option value="md">Markdown (.md)</option><option value="txt">Text (.txt)</option><option value="json">JSON response record (.json)</option></select></label><button type="button" onClick={download}>Download response</button></div>
}
