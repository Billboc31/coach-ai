import {useState} from 'react';
import {Dumbbell,FileText} from 'lucide-react';

type Thumbnail={url:string;credit:{authors:string[];name:string}};
export function ExerciseThumbnail({name,thumbnail,document=false}:{name:string;thumbnail?:Thumbnail|null;document?:boolean}){
 const [failed,setFailed]=useState(false);
 return <div className="exercise-thumbnail">{thumbnail&&!failed&&!document?<img src={thumbnail.url} alt={name} title={thumbnail.credit.authors.join(', ')+' · '+thumbnail.credit.name} loading="lazy" referrerPolicy="no-referrer" onError={()=>setFailed(true)}/>:document?<FileText size={28}/>:<Dumbbell size={28}/>}</div>;
}
