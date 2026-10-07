import {useState} from 'react';
import {Dumbbell,Search,Play,ExternalLink} from 'lucide-react';

export const movementLabels:Record<string,string>={auto:'Détection automatique',generic:'Autre mouvement',squat:'Squat',lunge:'Fente',hinge:'Charnière de hanche',press:'Développé couché',row:'Rowing',pullup:'Traction',curl:'Curl',plank:'Gainage',raise:'Élévation latérale'};
const normal=(s:string)=>s.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
export function movement(name:string,choice='auto'){
 if(choice!=='auto')return choice;
 const n=normal(name);
 if(/bulgar|split squat|fente|lunge/.test(n))return 'lunge';
 if(/squat/.test(n))return 'squat';
 if(/souleve de terre|deadlift|good morning|rdl/.test(n))return 'hinge';
 if(/developpe couche|bench press/.test(n))return 'press';
 if(/rowing|bucheron|tirage horizontal/.test(n))return 'row';
 if(/traction|pull.up|chin.up/.test(n))return 'pullup';
 if(/leg curl/.test(n))return 'generic';
 if(/curl|biceps/.test(n))return 'curl';
 if(/gainage|plank|planche/.test(n))return /lateral|side/.test(n)?'generic':'plank';
 if(/elevation.*laterale|lateral raise/.test(n))return 'raise';
 return 'generic';
}
type Pose={head:[number,number];lines:string[];equipment?:string[]};
const poses:Record<string,Pose[]>={
 squat:[{head:[56,23],lines:['56,36 56,76','56,45 76,55 86,46','56,76 46,110 46,138','56,76 68,110 68,138']},{head:[62,47],lines:['59,60 42,84','59,66 80,74 90,64','42,84 79,103 69,138','42,84 35,114 48,138']}],
 lunge:[{head:[60,23],lines:['60,36 60,76','60,44 47,69 47,91','60,44 73,69 73,91','60,76 42,108 29,138','60,76 79,110 91,138']},{head:[60,47],lines:['60,60 60,92','60,67 47,83 47,106','60,67 73,83 73,106','60,92 26,99 26,138','60,92 87,132 95,132']}],
 hinge:[{head:[60,23],lines:['60,36 60,76','60,44 48,74 48,90','60,44 72,74 72,90','60,76 48,110 43,138','60,76 71,110 76,138'],equipment:['38,91 82,91']},{head:[87,63],lines:['75,71 46,86','71,74 78,101 79,122','46,86 56,112 48,138'],equipment:['65,123 98,123']}],
 press:[{head:[27,92],lines:['40,92 78,92','47,90 53,69 64,83','78,92 91,111 91,138'],equipment:['35,104 85,104','55,83 82,83']},{head:[27,92],lines:['40,92 78,92','47,90 53,64 57,44','78,92 91,111 91,138'],equipment:['35,104 85,104','42,44 72,44']}],
 row:[{head:[85,50],lines:['76,59 46,84','69,65 78,88 78,118','46,84 55,109 49,138'],equipment:['68,119 88,119']},{head:[85,50],lines:['76,59 46,84','69,65 55,86 73,82','46,84 55,109 49,138'],equipment:['65,82 85,82']}],
 pullup:[{head:[60,50],lines:['60,63 60,99','60,67 40,40 31,19','60,67 80,40 89,19','60,99 49,126 51,138','60,99 71,126 69,138'],equipment:['17,18 103,18']},{head:[60,24],lines:['60,37 60,73','60,41 30,44 31,19','60,41 90,44 89,19','60,73 48,101 48,123','60,73 72,101 72,123'],equipment:['17,18 103,18']}],
 curl:[{head:[60,23],lines:['60,36 60,76','60,45 42,69 40,95','60,45 78,69 80,95','60,76 48,109 48,138','60,76 72,109 72,138'],equipment:['30,95 50,95','70,95 90,95']},{head:[60,23],lines:['60,36 60,76','60,45 42,69 38,46','60,45 78,69 82,46','60,76 48,109 48,138','60,76 72,109 72,138'],equipment:['28,46 48,46','72,46 92,46']}],
 plank:[{head:[24,89],lines:['35,98 79,111','40,100 33,125 20,125','79,111 102,125'],equipment:[]}],
 raise:[{head:[60,23],lines:['60,36 60,76','60,45 42,69 37,91','60,45 78,69 83,91','60,76 48,109 48,138','60,76 72,109 72,138'],equipment:['27,91 47,91','73,91 93,91']},{head:[60,23],lines:['60,36 60,76','60,45 35,48 13,51','60,45 85,48 107,51','60,76 48,109 48,138','60,76 72,109 72,138'],equipment:['8,45 8,57','112,45 112,57']}]
};
export function ExerciseDrawing({name,choice,mini=false}:{name:string;choice?:string;mini?:boolean}){
 const kind=movement(name,choice),frames=poses[kind];
 if(!frames)return <div className={'gym-drawing gym-drawing-generic '+(mini?'mini':'')} aria-label={'Illustration à choisir pour '+name}><Dumbbell size={mini?30:58}/>{!mini&&<span>Choisis un dessin depuis « Corriger »</span>}</div>;
 return <figure className={'gym-drawing '+(mini?'mini':'')}><svg role="img" aria-label={`${movementLabels[kind]} : schéma général${mini?'':frames.length===1?' en position de maintien':' en deux positions'}`} viewBox={`0 0 ${mini?120:frames.length*140} 158`}><title>{movementLabels[kind]+' · illustration générale'}</title>{(mini?frames.slice(-1):frames).map((p,i)=><g key={i} transform={`translate(${i*140} 0)`}><path d="M12 142H108" stroke="#cedbcc" strokeWidth="2"/>{p.equipment?.map((line,j)=><polyline key={'e'+j} points={line} fill="none" stroke="#b98b52" strokeWidth="7" strokeLinecap="round"/>)}<circle cx={p.head[0]} cy={p.head[1]} r="10" fill="#e2ecd7" stroke="#456745" strokeWidth="3"/>{p.lines.map((line,j)=><polyline key={j} points={line} fill="none" stroke={j===0?'#537e4b':'#76975d'} strokeWidth={j===0?10:6} strokeLinecap="round" strokeLinejoin="round"/>)}</g>)}</svg>{!mini&&<figcaption>{movementLabels[kind]} · schéma général. Vérifie la variante dans la vidéo.</figcaption>}</figure>;
}
// Public tutorial links checked 2026-10-07; suggestions are chosen by the user, never silently assigned.
const tutorials=[
 {id:'Ksnrn_fkrhc',title:'Squat à la barre · technique',source:'https://www.youtube.com/watch?v=Ksnrn_fkrhc',match:(n:string)=>/squat/.test(n)&&!(/bulgar|split|goblet|hack|jump|saut|pistol|front|air|overhead/.test(n))},
 {id:'J1ZOJo45TG8',title:'Développé couché · technique et progression',source:'https://www.youtube.com/watch?v=J1ZOJo45TG8',match:(n:string)=>/developpe couche|bench press/.test(n)&&!(/halter|incline|decline|serre|smith|guide/.test(n))},
 {id:'9bZV5jdMp2I',title:'Rowing à un bras avec haltère · Fitnessmith',source:'https://www.fitnessmith.fr/exercice-musculation-rowing-haltere-video/',match:(n:string)=>/bucheron|rowing.*(un bras|1 bras|unilateral)/.test(n)&&/halter|bucheron/.test(n)&&!(/incline|deux bras|2 bras|bilateral/.test(n))},
 {id:'HH9FQpjXw7A',title:'Fentes · technique et erreurs à éviter',source:'https://www.youtube.com/watch?v=HH9FQpjXw7A',match:(n:string)=>/fente/.test(n)&&!(/bulgar|saut|laterale|arriere|reverse|marchee/.test(n))}
];
export function VideoFinder({name,onSelect,selected}:{name:string;onSelect:(url:string)=>Promise<void>;selected:string|null}){
 const [query,setQuery]=useState(name+' technique exécution musculation'),[pending,setPending]=useState(''),[error,setError]=useState('');
 const suggestions=tutorials.filter(t=>t.match(normal(name)));
 async function choose(id:string){setPending(id);setError('');try{await onSelect('https://www.youtube.com/watch?v='+id);}catch(e){setError((e as Error).message);}finally{setPending('');}}
 return <div className="gym-video-finder"><h4>Trouver la bonne démonstration</h4><p className="hint">{name} · conserve le même matériel, la même prise et la même variante.</p>{suggestions.map(t=><div className="gym-video-suggestion" key={t.id}><Play size={25}/><div><strong>{t.title}</strong><a href={t.source} target="_blank" rel="noreferrer">Voir la démonstration <ExternalLink size={12}/></a></div><button className="outline" disabled={!!pending||selected===t.id} onClick={()=>void choose(t.id)}>{pending===t.id?'Enregistrement…':selected===t.id?'Sélectionnée':'Utiliser cette vidéo'}</button></div>)}<label>Recherche précise<input value={query} maxLength={250} onChange={e=>setQuery(e.target.value)}/></label><a className="outline gym-search-video" href={`https://www.youtube.com/results?search_query=${encodeURIComponent(query)}`} target="_blank" rel="noreferrer"><Search size={15}/>Chercher cette variante sur YouTube</a>{error&&<p className="error" role="alert">{error}</p>}</div>;
}
