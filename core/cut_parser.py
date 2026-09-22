import re,hashlib
from collections import defaultdict
import pandas as pd

def _text(raw): return raw.decode("latin1","ignore").replace("\r\n","\n").replace("\r","\n")
def _field(text,name):
 m=re.search(rf"^M,{re.escape(name)},([^,\n]*)",text,re.M|re.I); return m.group(1).strip() if m else None
def parse_cut(raw,name="archivo"):
 text=_text(raw); plot=text.split("\x0c",1)[0]
 h=re.search(r"M20\*([^*]+?)/L=([0-9.]+)IN/W=([0-9.]+)IN",plot,re.I)
 marker=h.group(1).strip() if h else (_field(text,"Marker Name") or name)
 ml=float(h.group(2)) if h else None; mw=float(h.group(3)) if h else None
 bm=re.search(r"(?:^|\n)B,(\d+),(\d+)",text)
 scale=(int(bm.group(2))/mw) if bm and mw else 100.0
 geom={}
 # Outer contour is between the second M15 and final M15 of each N record.
 starts=list(re.finditer(r"\*N(\d+)\*",plot))
 for i,m in enumerate(starts):
  seg=plot[m.end():starts[i+1].start() if i+1<len(starts) else len(plot)]
  parts=seg.split("*M15*")
  contour=parts[1] if len(parts)>1 else seg
  pts=[(int(x),int(y)) for x,y in re.findall(r"X(-?\d+)Y(-?\d+)",contour)]
  if pts:
   xs=[x for x,y in pts]; ys=[y for x,y in pts]
   geom[int(m.group(1))]={"points":pts,"xmin":min(xs),"xmax":max(xs),"ymin":min(ys),"ymax":max(ys),"width":(max(xs)-min(xs))/scale,"length":(max(ys)-min(ys))/scale}
 sec=text[text.find("N,0001"):] if "N,0001" in text else text
 matches=list(re.finditer(r"(?:^|\n)L,(\d+)\s*\n",sec))
 meta={}
 for i,m in enumerate(matches):
  block=sec[m.end():matches[i+1].start() if i+1<len(matches) else len(sec)]
  ds={int(k):v.strip() for k,v in re.findall(r"^D,(\d+),(.*)$",block,re.M)}
  if ds: meta[int(m.group(1))]=ds
 rows=[]
 for idx,ds in sorted(meta.items()):
  g=geom.get(idx); size=(ds.get(4) or "").replace("/R","").strip()
  rows.append({"Archivo":name,"ID":idx,"Modelo":ds.get(6) or "","Talla":size,"Pieza":ds.get(3) or "","Lado":ds.get(7) or "","Ancho":round(g["width"],4) if g else None,"Largo":round(g["length"],4) if g else None,"Puntos":len(g["points"]) if g else 0,"Estado":"OK" if g else "Sin geometría"})
 inst=pd.DataFrame(rows)
 # Counts in a marker are instances, not necessarily quantity per garment.
 lib=[]
 if not inst.empty:
  for (model,size,piece),grp in inst.groupby(["Modelo","Talla","Pieza"],dropna=False):
   lib.append({"Modelo":model,"Talla":size,"Pieza":piece,"InstanciasCUT":len(grp),"RepeticionesTalla":1,"Cantidad":len(grp),"Ancho":round(float(grp.Ancho.max()),2),"Largo":round(float(grp.Largo.max()),2),"Unidad":"IN","Confianza":100 if grp.Estado.eq("OK").all() else 65})
 diag={"Archivo":name,"Marcador":marker,"Modelo":", ".join(sorted(inst.Modelo.unique())) if not inst.empty else "No detectado","AnchoMarcador":mw,"LargoMarcador":ml,"Utilizacion":_field(text,"MARKER UTILTIZATION"),"Unidad":"IN" if h else "Desconocida","Geometrias":len(geom),"Metadatos":len(meta),"Relacionados":sum(i in geom for i in meta),"Escala":scale,"Estado":"Lectura completa" if geom and len(geom)==len(meta) else "Revisar"}
 return {"diagnostic":diag,"instances":inst,"library":pd.DataFrame(lib),"geometry":geom,"sha":hashlib.sha1(raw).hexdigest()[:12]}

def normalize_library(df):
 out=df.copy(); reps=pd.to_numeric(out["RepeticionesTalla"],errors="coerce").fillna(1).clip(lower=1)
 out["Cantidad"]=(pd.to_numeric(out["InstanciasCUT"],errors="coerce").fillna(0)/reps).round().astype(int)
 return out[["Modelo","Talla","Pieza","Cantidad","Ancho","Largo","Unidad","Confianza"]]
