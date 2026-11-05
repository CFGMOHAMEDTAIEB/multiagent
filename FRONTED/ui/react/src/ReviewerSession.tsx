import {useEffect} from 'react'
const sessions=new Map<string,any>()
const key=(s:any)=>s.client.id+':'+s.project
export const reviewerSession=(s:any)=>{const value=sessions.get(key(s));return value&&value.expires_at>Date.now()?value:null}
// Authentication controls are intentionally absent from every application page.
export default function ReviewerSession({s,onChange}:{s:any;onChange?:(session:any)=>void}){
 useEffect(()=>{const update=()=>onChange?.(reviewerSession(s));window.addEventListener('sx-reviewer-session',update);update();return()=>window.removeEventListener('sx-reviewer-session',update)},[s.client.id,s.project])
 return null
}
