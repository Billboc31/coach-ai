import {useEffect,useRef,useState} from 'react';
import type {SetLog} from './gym';

export function GymProgression({name,rows,onChoose,onCancel}:{name:string;rows:SetLog[];onChoose:(increase:number|null)=>void;onCancel:()=>void}){
 const dialog=useRef<HTMLDialogElement>(null),[increase,setIncrease]=useState('');
 useEffect(()=>{const node=dialog.current;node?.showModal();return()=>node?.close();},[]);
 const delta=Number(increase),valid=increase!==''&&Number.isFinite(delta)&&delta>0&&delta<=2000&&rows.every(s=>s.weight==null||s.weight+delta<=2000);
 return <dialog ref={dialog} className="gym-progression-dialog" aria-labelledby="gym-progression-title" onCancel={onCancel}>
  <h2 id="gym-progression-title">Augmenter la charge la prochaine fois ?</h2><p>{name} · toutes les séries sont validées.</p>
  <p>Ajoute le même nombre de kg à chaque charge connue. Pour une montée progressive, les écarts entre les séries restent conservés.</p>
  <label>Augmentation · kg<input autoFocus type="number" inputMode="decimal" min={0.01} max={2000} step="any" value={increase} onChange={ev=>setIncrease(ev.target.value)}/></label>
  {valid&&<p className="gym-progression-preview">Prochaine séance : {rows.map(s=>s.weight==null?'Poids inconnu':`${s.weight+delta} kg`).join(' · ')}</p>}
  <div><button className="primary" disabled={!valid} onClick={()=>onChoose(delta)}>Oui, augmenter</button><button className="outline" onClick={()=>onChoose(0)}>Garder les charges</button><button className="text-button" onClick={()=>onChoose(null)}>Décider plus tard</button><button className="text-button" onClick={onCancel}>Revenir à l’exercice</button></div>
 </dialog>;
}
