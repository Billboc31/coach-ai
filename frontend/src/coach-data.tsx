export type CoachDataRequest = {
  id:string; activity_id:string; activity_name:string; activity_date:string;
  fields:string[]; reason:string; status:'proposed'|'ready'; chat_message_id:number;
};
const labels:Record<string,string> = {
  all:'Détails disponibles',laps:'Tours',heart_rate:'Fréquence cardiaque',speed:'Vitesse / allure',
  power:'Puissance',run_cadence:'Cadence de course',bike_cadence:'Cadence de pédalage',
  elevation:'Altitude',temperature:'Température',ground_contact:'Contact au sol',stride_length:'Foulée',
};
export function CoachDataCard({request,busy,canAnalyze,onAnalyze}:{
  request:CoachDataRequest;busy:boolean;canAnalyze:boolean;onAnalyze:(request:CoachDataRequest)=>void;
}){
 return <section className="coach-data-card" aria-label="Données Garmin demandées">
  <small>DONNÉES GARMIN</small><strong>{request.activity_name}{request.activity_date?` · ${request.activity_date}`:''}</strong>
  {request.reason&&<p>{request.reason}</p>}
  <div className="sport-tags">{request.fields.map(f=><span key={f}>{labels[f]||f}</span>)}</div>
  <button className="outline" disabled={busy||!canAnalyze} onClick={()=>onAnalyze(request)}>
   {busy?'Chargement / analyse en cours…':request.status==='ready'?'Analyser les données chargées':'Récupérer et analyser'}
  </button>
  <small>{request.status==='ready'?'Détails chargés.':'Lecture Garmin au clic.'} L’analyse envoie les mesures utiles à OpenAI et utilise ton forfait. Courbes selon les capteurs disponibles.</small>
 </section>;
}
