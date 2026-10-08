/** Small text-only renderer: React escapes all input; no raw HTML or remote media. */
export function CoachReply({text}:{text:string}){
 return <div className="coach-reply">{text.split(/\n\s*\n/).map((paragraph,i)=><p key={i}>{paragraph.split(/(\*\*[^*\n]+\*\*)/g).map((part,j)=>part.startsWith('**')&&part.endsWith('**')?<strong key={j}>{part.slice(2,-2)}</strong>:part)}</p>)}</div>;
}
