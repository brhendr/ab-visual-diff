"""Visible DOM and screenshot comparison utilities."""
from collections import Counter
from difflib import SequenceMatcher
from PIL import Image, ImageChops, ImageEnhance, ImageDraw

DOM_CAPTURE = r'''() => {
 const els = document.querySelectorAll('h1,h2,h3,h4,p,a,button,[role="button"],input[type="submit"],label,img');
 const out=[], used=new Map();
 const norm = x => (x||'').replace(/\s+/g,' ').trim().slice(0,220);
 for(const el of els){
  if(out.length>=900) break;
  if(el.closest('[hidden],[aria-hidden="true"]')) continue;
  const s=getComputedStyle(el),r=el.getBoundingClientRect();
  if(s.display==='none'||s.visibility==='hidden'||+s.opacity===0||!r.width||!r.height||r.bottom<0||r.top>innerHeight) continue;
  const tag=el.tagName.toLowerCase();
  const val=norm(el.getAttribute('aria-label')||(tag==='img'?el.getAttribute('alt'):el.innerText)||el.value);
  const href=tag==='a'?el.getAttribute('href'):null;
  const src=tag==='img'?(el.currentSrc||el.getAttribute('src')):null;
  if(!val&&!href&&!src) continue;
  let node=el,path=[];
  for(let n=0;node&&n<6;n++,node=node.parentElement){
   const siblings=node.parentElement?Array.from(node.parentElement.children).filter(x=>x.tagName===node.tagName):[node];
   path.unshift(tag===node.tagName.toLowerCase()?node.tagName.toLowerCase()+':'+siblings.indexOf(node):node.tagName.toLowerCase()+':'+siblings.indexOf(node));
   if(node.id){path.unshift('#'+node.id);break;}
  }
  const key=tag+'@'+(el.getAttribute('data-testid')||el.id||path.join('/'));
  const k=key+':'+(used.get(key)||0);used.set(key,(used.get(key)||0)+1);
  out.push({key:k,tag,text:val,href,src:src?src.slice(0,300):null,box:[Math.round(r.x),Math.round(r.y),Math.round(r.width),Math.round(r.height)]});
 }
 return out;
}'''

def compare_elements(a,b,limit=100):
    aa={x['key']:x for x in a};bb={x['key']:x for x in b}
    changes=[]
    for key in aa.keys()|bb.keys():
        x=aa.get(key);y=bb.get(key)
        if x and y:
            fields=[f for f in ('text','href','src') if (x.get(f) or '')!=(y.get(f) or '')]
            if not fields:continue
            changes.append(dict(type='modified',tag=x['tag'],key=key,before=x.get('text') or x.get('src') or x.get('href') or '',after=y.get('text') or y.get('src') or y.get('href') or '',fields=fields,box_a=x['box'],box_b=y['box']))
        else:
            v=x or y
            if len(v.get('text') or '')<12 and not v.get('src'):continue
            changes.append(dict(type='removed' if x else 'added',tag=v['tag'],key=key,before=(v.get('text') or v.get('src') or '') if x else '',after=(v.get('text') or v.get('src') or '') if y else '',fields=['presence'],box_a=v['box'] if x else None,box_b=v['box'] if y else None))
    priority={'h1':0,'h2':1,'button':2,'a':3,'h3':4,'img':5,'p':6}
    return sorted(changes,key=lambda c:(priority.get(c['tag'],9),c['type']!='modified',c['key']))[:limit]

def summarize_groups(groups,by_id):
    if len(groups)<2:return []
    base=groups[0][:5];out=[]
    for i,g in enumerate(groups[1:],2):
        counts=Counter()
        for a in base:
            for b in g[:5]:
                for c in compare_elements(by_id[a].get('elements',[]),by_id[b].get('elements',[])):
                    if c['type']=='modified':counts[(c['tag'],c['before'],c['after'])]+=1
        out.append({'group':i,'compared_with':1,'repeatable_changes':[dict(element=k[0],before=k[1],after=k[2],count=n,out_of=len(base)*min(5,len(g))) for k,n in counts.most_common(15)]})
    return out

def highlight_boxes(img,changes,side='b'):
    output=img.convert('RGB').copy();draw=ImageDraw.Draw(output)
    for c in changes:
        box=c.get('box_'+side)
        if box:
            x,y,w,h=box
            if w>0 and h>0:draw.rectangle([x,y,x+w,y+h],outline='#FF8C00',width=3)
    return output

def image_difference(a,b):
    w=min(a.width,b.width);h=min(a.height,b.height)
    diff=ImageChops.difference(a.convert('RGB').crop((0,0,w,h)),b.convert('RGB').crop((0,0,w,h)))
    ratio=100*sum(1 for pixel in diff.getdata() if max(pixel)>35)/(w*h)
    return ratio,ImageEnhance.Contrast(diff).enhance(3)
