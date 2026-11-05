import { useEffect, useState } from 'react'
type File = {name:string; size:number}
export default function GeneratedFiles({agent, sources, answer}: {agent:string; sources:string[]; answer?:string}) {
  const [files, setFiles] = useState<File[]>([])
  const [filename, setFilename] = useState('result')
  const [format, setFormat] = useState('json')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [preview, setPreview] = useState<{name:string; content:string; truncated:boolean} | null>(null)
  async function refresh() {
    const response = await fetch('/generated/' + agent)
    if (!response.ok) throw new Error('Could not load generated files.')
    setFiles(await response.json())
  }
  useEffect(() => { void refresh().catch(e => setError(String(e))) }, [agent])
  async function generate(fromSources: boolean) {
    setBusy(true); setError('')
    try {
      const response = await fetch('/generated/' + agent, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(fromSources ? {filename, format:'json', sources} : {filename, format, content:answer})})
      const data = await response.json()
      if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail))
      await refresh()
      await show(data.name)
    } catch (e) { setError(e instanceof Error ? e.message : String(e)) }
    finally { setBusy(false) }
  }
  async function show(name:string) {
    try {
      const response = await fetch('/generated/' + agent + '/' + encodeURIComponent(name) + '?preview=true')
      if (!response.ok) throw new Error('Could not preview the generated file.')
      setPreview({name, ...await response.json()})
    } catch (e) { setError(String(e)) }
  }
  return <section className="file-panel generated-panel">
    <h3>Generated files</h3>
    <p>Create a lossless JSON copy of selected documents, or save the latest agent answer. Files remain available after refreshing.</p>
    <div className="download-response">
      <label>Output filename<input aria-label="Output filename" value={filename} maxLength={80} onChange={e => setFilename(e.target.value)}/></label>
      <button disabled={busy || !sources.length || !filename.trim()} onClick={() => void generate(true)}>Convert selected files to JSON</button>
    </div>
    <p>JSON conversion preserves the complete text in a documents array. It does not summarize or reinterpret your content.</p>
    <div className="download-response">
      <label>Answer format<select value={format} onChange={e => setFormat(e.target.value)}><option value="json">JSON (validated)</option><option value="md">Markdown</option><option value="txt">Text</option></select></label>
      <button disabled={busy || !answer || !filename.trim()} onClick={() => void generate(false)}>Save latest answer as file</button>
    </div>
    {busy && <p role="status">Creating file…</p>}
    {error && <p role="alert" className="error">{error}</p>}
    {!files.length && <p>No generated files yet.</p>}
    <ul>{files.map(file => <li key={file.name}><span style={{flex:1, overflowWrap:'anywhere'}}>{file.name}</span><span>{Math.ceil(file.size / 1024)} KB</span><button onClick={() => void show(file.name)}>Preview</button><a href={'/generated/' + agent + '/' + encodeURIComponent(file.name)} download>Download</a></li>)}</ul>
    {preview && <div><h4>{preview.name}</h4><button onClick={() => setPreview(null)}>Close preview</button>{preview.truncated && <p>Preview shows the first 20,000 characters. Download contains the full file.</p>}<pre style={{maxHeight:320, overflow:'auto'}}>{preview.content}</pre></div>}
  </section>
}
