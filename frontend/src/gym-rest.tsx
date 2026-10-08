import {useEffect, useState} from 'react';

// Parse only a single explicit duration; ranges and free text stay manual.
export function restSeconds(raw:string):number|null {
 const text=raw.trim().toLowerCase();
 const seconds=text.match(/^(\d+)\s*(?:s|sec|secs|secondes?|''|″)$/);
 const minutes=text.match(/^(\d+)\s*(?:min|minutes?|'|′)$/);
 const mixed=text.match(/^(\d+)\s*['′:]\s*(\d{1,2})\s*(?:s|''|″)?$/);
 const value=seconds?Number(seconds[1]):minutes?Number(minutes[1])*60:mixed&&Number(mixed[2])<60?Number(mixed[1])*60+Number(mixed[2]):null;
 return value!=null&&value>0&&value<=7200?value:null;
}
export function useRestTimer(){
 const [deadline,setDeadline]=useState<number|null>(null),[remaining,setRemaining]=useState<number|null>(null),[custom,setCustom]=useState('');
 useEffect(()=>{if(deadline==null)return;const tick=()=>{const next=Math.max(0,Math.ceil((deadline-Date.now())/1000));setRemaining(next);if(next===0)setDeadline(null);};tick();const interval=setInterval(tick,250);return()=>clearInterval(interval);},[deadline]);
 function start(raw:string){const override=Number(custom);const seconds=custom!==''&&Number.isInteger(override)&&override>0&&override<=7200?override:restSeconds(raw);if(seconds!=null){setRemaining(seconds);setDeadline(Date.now()+seconds*1000);}}
 const display=remaining==null?'Prêt':remaining===0?'Repos terminé':`${Math.floor(remaining/60)}:${String(remaining%60).padStart(2,'0')}`;
 const view=<section className="session-rest" aria-label="Minuteur de repos"><div><b>Repos</b><strong role="timer" aria-live="off">{display}</strong></div><details><summary>Régler la durée</summary><label>Durée personnalisée · secondes<input type="number" inputMode="numeric" min={1} max={7200} step={1} value={custom} placeholder="Selon le programme" onChange={ev=>setCustom(ev.target.value)}/></label><small>Départ à la validation si une durée précise est connue. Sinon, renseigne la durée avant de valider.</small></details><div className="session-rest-actions"><button className="outline" onClick={()=>deadline!=null?setDeadline(null):remaining!=null&&remaining>0?setDeadline(Date.now()+remaining*1000):undefined} disabled={remaining==null||remaining===0}>{deadline!=null?'Pause':'Reprendre'}</button><button className="outline" onClick={()=>{setDeadline(null);setRemaining(null);}}>Passer le repos</button></div></section>;
 return {start,view};
}
