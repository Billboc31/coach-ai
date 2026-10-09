import {useEffect, useRef, useState} from 'react';
import type {FormEvent} from 'react';
import './garmin-login.css';

type Attempt = {status:string;id?:string;message?:string;expires_at?:number};
const activeStatuses = ['connecting','awaiting_mfa','verifying','cancelling'];

async function request(path='', body?:object):Promise<Attempt> {
  const response = await fetch('/api/garmin/login'+path, {
    method:body?'POST':'GET',
    headers:{'Content-Type':'application/json'},
    ...(body?{body:JSON.stringify(body)}:{}),
  });
  if(!response.ok){
    let message=response.status===401?'Reconnecte ton espace.':'Connexion indisponible.';
    try { const value=await response.json();if(typeof value.detail==='string')message=value.detail; } catch { /* no raw provider response */ }
    throw new Error(message);
  }
  return response.json();
}

export function GarminLogin({onChanged,onActive}:{onChanged:()=>Promise<void>;onActive:(active:boolean)=>void}) {
  const [attempt,setAttempt]=useState<Attempt>({status:'idle'});
  const [email,setEmail]=useState(''),[password,setPassword]=useState(''),[code,setCode]=useState('');
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[visible,setVisible]=useState(false);
  const callback=useRef(onChanged),completed=useRef('');
  callback.current=onChanged;
  const active=activeStatuses.includes(attempt.status);
  useEffect(()=>{onActive(active);return()=>onActive(false);},[active,onActive]);

  async function accept(next:Attempt){
    setAttempt(next);
    if(next.status==='completed'&&next.id!==completed.current){
      completed.current=next.id||'';
      try { await callback.current(); } catch { setError('Session enregistrée. Actualise la page pour afficher son état.'); }
    }
  }
  useEffect(()=>{
    let alive=true;
    void request().then(next=>{if(alive)void accept(next);}).catch(e=>{if(alive)setError((e as Error).message);});
    return()=>{alive=false;};
  },[]);
  useEffect(()=>{
    if(!active)return;
    let alive=true,pending=false;
    const timer=setInterval(()=>{
      if(pending)return;
      pending=true;
      void request().then(next=>{if(alive)void accept(next);}).catch(e=>{if(alive)setError((e as Error).message);}).finally(()=>{pending=false;});
    },1500);
    return()=>{alive=false;clearInterval(timer);};
  },[active]);

  async function run(fn:()=>Promise<Attempt>){
    setBusy(true);setError('');
    try { await accept(await fn()); } catch(e){setError((e as Error).message);}
    finally {setBusy(false);}
  }
  function connect(event:FormEvent){
    event.preventDefault();
    const submitted=password;
    setPassword('');setVisible(false);setCode('');
    void run(()=>request('',{email:email.trim(),password:submitted}));
  }
  function verify(event:FormEvent){
    event.preventDefault();
    const submitted=code.trim();setCode('');
    void run(()=>request('/mfa',{id:attempt.id,code:submitted}));
  }

  return <section className="garmin-login" aria-label="Connexion Garmin directe">
    <h3>Connecter Garmin ici</h3>
    <p>Essaie depuis ton téléphone, sans ordinateur. Tes identifiants sont envoyés à ce serveur pour la connexion ; le mot de passe et le code ne sont pas enregistrés.</p>
    <p className="hint">Garmin peut refuser une connexion depuis Railway (403). Un échec conserve la session précédente ; l’import depuis un ordinateur reste disponible.</p>
    {!active&&<form onSubmit={connect}>
      <label>E-mail Garmin<input type="email" autoComplete="username" required maxLength={254} value={email} onChange={e=>setEmail(e.target.value)} disabled={busy}/></label>
      <label>Mot de passe Garmin<input type={visible?'text':'password'} autoComplete="current-password" required maxLength={1024} value={password} onChange={e=>setPassword(e.target.value)} disabled={busy}/></label>
      <button type="button" className="text-button garmin-password-toggle" disabled={busy} onClick={()=>setVisible(!visible)}>{visible?'Masquer':'Afficher'} le mot de passe</button>
      <button type="submit" className="primary" disabled={busy||!email.trim()||!password}>{busy?'Envoi…':attempt.status==='completed'?'Reconnecter Garmin':'Essayer la connexion Garmin'}</button>
    </form>}
    {attempt.status==='awaiting_mfa'&&<form onSubmit={verify}>
      <label>Code envoyé par Garmin<input type="text" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{4,12}" minLength={4} maxLength={12} required value={code} onChange={e=>setCode(e.target.value.replace(/\D/g,''))} disabled={busy}/></label>
      <p className="hint">Saisis le code reçu par e-mail ou le moyen indiqué par Garmin. La tentative expire au bout de cinq minutes.</p>
      <button type="submit" className="primary" disabled={busy||code.length<4}>Valider le code Garmin</button>
    </form>}
    {attempt.message&&<p className={attempt.status==='completed'?'connection-success':attempt.status==='failed'?'error':'hint'} role={attempt.status==='failed'?'alert':'status'}>{attempt.message}</p>}
    {active&&<button type="button" className="outline" disabled={busy||attempt.status==='cancelling'} onClick={()=>void run(()=>request('/cancel',{id:attempt.id}))}>{attempt.status==='cancelling'?'Annulation en cours…':'Annuler la connexion'}</button>}
    {error&&<p className="error" role="alert">{error}</p>}
  </section>;
}
