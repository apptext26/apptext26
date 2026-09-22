import math,random,hashlib,json
from models import PieceInstance,Block,Candidate

def expand(lib,reps):
 out=[]
 for _,r in lib.iterrows():
  key=f"{r.Modelo}|{r.Talla}"; n=int(reps.get(key,0))*int(r.Cantidad)
  for i in range(n): out.append(PieceInstance(f"{key}|{r.Pieza}|{i+1}",str(r.Modelo),str(r.Talla),str(r.Pieza),float(r.Ancho),float(r.Largo)))
 return out
def pack(pieces,width,order,best=False):
 bs=[]
 for p in order:
  ok=[b for b in bs if b.used_width+p.width<=width+1e-9]
  if ok: (min(ok,key=lambda b:width-b.used_width-p.width) if best else ok[0]).pieces.append(p)
  else:
   if p.width>width: raise ValueError(f"{p.uid} excede el ancho")
   bs.append(Block(len(bs)+1,width,[p]))
 return bs
def distributions(pieces,width,n=20):
 variants=[]
 for name,key in [("ancho",lambda p:(p.width,p.length)),("largo",lambda p:(p.length,p.width)),("area",lambda p:(p.area,p.width))]:
  o=sorted(pieces,key=key,reverse=True); variants += [(name+"_first_fit",pack(pieces,width,o)),(name+"_best_fit",pack(pieces,width,o,True))]
 rng=random.Random(42)
 for i in range(n):
  o=list(pieces);rng.shuffle(o);variants.append((f"aleatoria_{i+1}",pack(pieces,width,o,True)))
 return variants
def signature(layers,reps,blocks):
 content=[]
 for b in blocks: content.append(tuple(sorted((p.model,p.size,p.piece,round(p.width,3),round(p.length,3)) for p in b.pieces)))
 return hashlib.sha1(json.dumps([layers,sorted(reps.items()),sorted(content)],sort_keys=True).encode()).hexdigest()
def generate(lib,req,width,lmin,lmax,step=1,maxover=25,short=True,random_n=20,maxn=100,weights=None):
 weights=weights or {"g":.4,"c":.3,"o":.15,"p":.15}; raw=[]
 rq=req.groupby(["Modelo","Talla"],as_index=False).Unidades.sum()
 for layers in range(int(lmin),int(lmax)+1,int(step)):
  opts=[]
  for _,r in rq.iterrows():
   q=float(r.Unidades)/layers; z={math.ceil(q)}; z.add(math.floor(q) if short else math.ceil(q));opts.append((f"{r.Modelo}|{r.Talla}",int(r.Unidades),sorted(z)))
  combos=[({}, {})]
  for k,u,zs in opts:
   combos=[({**a,k:z},{**d,k:u}) for a,d in combos for z in zs]
  for reps,dem in combos:
   prod={k:v*layers for k,v in reps.items()}; over={k:max(0,prod[k]-dem[k]) for k in dem}; falt={k:max(0,dem[k]-prod[k]) for k in dem}; td=sum(dem.values())
   if sum(over.values())/td*100>maxover:continue
   pcs=expand(lib,reps)
   if not pcs:continue
   for st,bs in distributions(pcs,width,random_n):
    length=sum(b.length for b in bs);area=sum(p.area for p in pcs);eff=area/(width*length);comp=sum(min(prod[k],dem[k]) for k in dem)/td;low=max(0,1-sum(over.values())/td);oper=max(0,1-(len(bs)-1)/len(pcs));score=100*(weights['g']*eff+weights['c']*comp+weights['o']*low+weights['p']*oper)
    raw.append((signature(layers,reps,bs),Candidate('',layers,reps,prod,falt,over,bs,st,[],area,length,eff,comp,score)))
 groups={}
 for sig,c in raw:
  if sig not in groups:groups[sig]=c
  elif c.strategy not in groups[sig].equivalent_strategies:groups[sig].equivalent_strategies.append(c.strategy)
 unique=sorted(groups.values(),key=lambda c:(-c.total_score,c.estimated_length))[:maxn]
 for i,c in enumerate(unique,1):c.candidate_id=f"CAND-{i:05d}"
 return unique,{"evaluados":len(raw),"unicos":len(groups),"duplicados":len(raw)-len(groups)}
