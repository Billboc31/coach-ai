/** Original schematic artwork. Highlights use documented wger groups, never inferred targets. */
const labels:Record<string,string>={Abs:'Abdominaux',Biceps:'Biceps',Brachialis:'Brachial',Calves:'Mollets',Chest:'Pectoraux',Glutes:'Fessiers',Hamstrings:'Ischio-jambiers',Lats:'Grand dorsal','Obliquus externus abdominis':'Obliques',Quads:'Quadriceps','Serratus anterior':'Dentelé antérieur',Shoulders:'Épaules',Soleus:'Soléaire',Trapezius:'Trapèzes',Triceps:'Triceps'};
export function muscleLabel(name:string){return labels[name]||name;}
const front:Record<string,string[]>={
 Shoulders:['M52 89 Q63 80 73 92 L66 110 L48 111 Z','M128 89 Q117 80 107 92 L114 110 L132 111 Z'],
 Chest:['M73 94 L87 96 L87 125 Q69 134 62 117 Z','M107 94 L93 96 L93 125 Q111 134 118 117 Z'],
 Biceps:['M47 116 L62 119 L55 150 L43 157 Q39 137 47 116Z','M133 116 L118 119 L125 150 L137 157 Q141 137 133 116Z'],
 Brachialis:['M43 157 L55 150 L52 164 L41 170Z','M137 157 L125 150 L128 164 L139 170Z'],
 Abs:['M78 135 L102 135 L102 186 L90 194 L78 186 Z'],
 'Obliquus externus abdominis':['M66 137 L74 141 L74 183 L63 199 L60 174Z','M114 137 L106 141 L106 183 L117 199 L120 174Z'],
 'Serratus anterior':['M62 122 L74 129 L73 139 L63 135Z','M118 122 L106 129 L107 139 L117 135Z'],
 Quads:['M61 237 L84 238 L83 293 L73 306 L59 295Z','M119 237 L96 238 L97 293 L107 306 L121 295Z'],
};
const back:Record<string,string[]>={
 Trapezius:['M79 70 L101 70 L116 91 L103 110 L90 124 L77 110 L64 91Z'],
 Shoulders:['M52 89 Q63 80 73 92 L66 110 L48 111 Z','M128 89 Q117 80 107 92 L114 110 L132 111 Z'],
 Triceps:['M47 116 L62 119 L55 158 L43 161 Q39 137 47 116Z','M133 116 L118 119 L125 158 L137 161 Q141 137 133 116Z'],
 Lats:['M63 113 L85 133 L85 177 L71 187 L60 149Z','M117 113 L95 133 L95 177 L109 187 L120 149Z'],
 Glutes:['M65 206 L87 203 L87 239 Q67 249 59 235Z','M115 206 L93 203 L93 239 Q113 249 121 235Z'],
 Hamstrings:['M61 246 L84 247 L82 297 L73 306 L60 294Z','M119 246 L96 247 L98 297 L107 306 L120 294Z'],
 Calves:['M62 312 L80 312 Q86 336 77 347 L64 346 Q57 331 62 312Z','M118 312 L100 312 Q94 336 103 347 L116 346 Q123 331 118 312Z'],
 Soleus:['M65 350 L77 350 L74 366 L67 366Z','M115 350 L103 350 L106 366 L113 366Z'],
};
function Body({rear,main,secondary}:{rear:boolean;main:Set<string>;secondary:Set<string>}){
 const groups=rear?back:front;
 return <svg viewBox="0 0 180 400" role="img" aria-label={`${rear?'Dos':'Face'} : ${[...main].map(muscleLabel).join(', ')||'muscles principaux non renseignés'}`}><circle cx="90" cy="42" r="23" fill="var(--muscle-neutral)"/><path d="M79 65 L101 65 L103 77 Q132 82 137 113 L145 154 L155 198 L146 207 L135 185 L124 146 L119 181 L123 216 L123 261 L119 307 L124 342 L115 373 L126 380 L123 386 L101 384 L100 358 L95 319 L90 274 L85 319 L80 358 L79 384 L57 386 L54 380 L65 373 L56 342 L61 307 L57 261 L57 216 L61 181 L56 146 L45 185 L34 207 L25 198 L35 154 L43 113 Q48 82 77 77Z" fill="var(--muscle-neutral)" stroke="var(--muscle-outline)" strokeWidth="1.5"/>{Object.entries(groups).map(([muscle,paths])=><g key={muscle} fill={main.has(muscle)?'var(--muscle-primary)':secondary.has(muscle)?'var(--muscle-secondary)':'var(--muscle-rest)'} stroke="var(--muscle-outline)" strokeWidth="1"><title>{muscleLabel(muscle)+(main.has(muscle)?' — principal':secondary.has(muscle)?' — secondaire':'')}</title>{paths.map((d,i)=><path d={d} key={i}/>)}</g>)}<text x="90" y="399" textAnchor="middle" fill="currentColor" fontSize="12">{rear?'Dos':'Face'}</text></svg>;
}
export function MuscleMap({primary,secondary=[]}:{primary:string[];secondary?:string[]}){
 const main=new Set(primary),support=new Set(secondary.filter(m=>!main.has(m)));
 return <section className="muscle-map"><h5>Muscles travaillés</h5><div className="muscle-map-bodies"><Body rear={false} main={main} secondary={support}/><Body rear main={main} secondary={support}/></div><div className="muscle-map-legend"><p><i className="muscle-main-dot"/><strong>Principaux :</strong> {primary.length?primary.map(muscleLabel).join(', '):'Non renseignés dans la base'}</p><p><i className="muscle-secondary-dot"/><strong>Secondaires :</strong> {support.size?[...support].map(muscleLabel).join(', '):'Non renseignés dans la base'}</p></div><p className="hint">Silhouette schématique face/dos · groupes musculaires documentés par wger, sans estimation d’intensité.</p></section>;
}
