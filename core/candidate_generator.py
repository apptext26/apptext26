import math
import pandas as pd
from models import Candidate
from .piece_expander import expand_pieces
from .block_optimizer import build_distributions

def _rep_options(units, layers, allow_shortage=True, allow_over=True):
    raw = units / layers
    opts = set()
    if allow_shortage: opts.add(max(0, math.floor(raw)))
    if allow_over: opts.add(math.ceil(raw))
    if not opts: opts.add(round(raw))
    return sorted(opts)

def generate_candidates(library, requirements, fabric_width, layers_min, layers_max,
                        layer_step=1, max_overproduction_pct=25.0,
                        allow_shortage=True, random_iterations=20, max_candidates=100,
                        weights=None):
    weights = weights or {"geometry": .40, "compliance": .30, "low_over": .15, "operability": .15}
    req = requirements.groupby(["Modelo","Talla"], as_index=False)["Unidades"].sum()
    candidates, seq = [], 1
    for layers in range(int(layers_min), int(layers_max)+1, int(layer_step)):
        option_rows = []
        for _, r in req.iterrows():
            key = f"{r['Modelo']}|{r['Talla']}"
            option_rows.append((key, int(r["Unidades"]), _rep_options(int(r["Unidades"]), layers, allow_shortage, True)))
        combos = [({}, {})]
        for key, units, options in option_rows:
            nxt=[]
            for reps, demands in combos:
                for n in options:
                    nr=dict(reps); nr[key]=n
                    nd=dict(demands); nd[key]=units
                    nxt.append((nr, nd))
            combos=nxt
        for repetitions, demands in combos:
            production={k:v*layers for k,v in repetitions.items()}
            shortages={k:max(0,demands[k]-production[k]) for k in demands}
            over={k:max(0,production[k]-demands[k]) for k in demands}
            total_demand=sum(demands.values())
            total_over=sum(over.values())
            if total_demand and total_over/total_demand*100 > max_overproduction_pct: continue
            pieces=expand_pieces(library, repetitions)
            if not pieces: continue
            for strategy, blocks in build_distributions(pieces, fabric_width, random_iterations):
                length=sum(b.length for b in blocks)
                area=sum(p.area for p in pieces)
                efficiency=area/(fabric_width*length) if length else 0
                compliance=sum(min(production[k],demands[k]) for k in demands)/total_demand if total_demand else 1
                low_over=max(0, 1-total_over/total_demand) if total_demand else 1
                operability=max(0, 1-(len(blocks)-1)/max(1,len(pieces)))
                score=100*(weights["geometry"]*efficiency+weights["compliance"]*compliance+weights["low_over"]*low_over+weights["operability"]*operability)
                candidates.append(Candidate(f"CAND-{seq:05d}",layers,repetitions,production,shortages,over,blocks,strategy,area,length,efficiency,compliance,score)); seq+=1
    candidates.sort(key=lambda c:(-c.total_score,c.estimated_length,-c.rectangular_efficiency))
    return candidates[:max_candidates]
