from pathlib import Path
from core.cut_parser import parse_cut,normalize_library
from core.optimizer import generate
import pandas as pd
def test_small_cut():
 p=parse_cut(Path('/mnt/data/TEST PEQUEÑO.TXT').read_bytes(),'small')
 assert p['diagnostic']['Geometrias']==4 and p['diagnostic']['Metadatos']==4
 lib=normalize_library(p['library']); assert dict(zip(lib.Pieza,lib.Cantidad))=={'BK':1,'FT':1,'SL':2}
 assert float(lib[lib.Pieza=='BK'].Ancho.iloc[0])==31.37
def test_full_cut():
 p=parse_cut(Path('/mnt/data/TEST TEST.TXT').read_bytes(),'full')
 assert p['diagnostic']['Geometrias']==24 and p['diagnostic']['Metadatos']==24
 assert set(p['library'].Talla)=={'XS','S','M','L','XL','XXL'}
def test_dedup():
 lib=pd.read_csv('/mnt/data/predictor_accumark_v2/data/piezas_ejemplo.csv');req=pd.DataFrame([{'Modelo':'3238OW','Talla':'L','Unidades':100}])
 cs,s=generate(lib,req,80,50,50,random_n=20);assert s['duplicados']>0 and len(cs)==s['unicos']
