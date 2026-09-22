import pandas as pd
from core.piece_expander import expand_pieces
from core.block_optimizer import build_distributions
from core.candidate_generator import generate_candidates

def library():
    return pd.DataFrame([
        {"Modelo":"MODELO-001","Talla":"L","Pieza":"FT","Cantidad":1,"Ancho":23,"Largo":21},
        {"Modelo":"MODELO-001","Talla":"L","Pieza":"BK","Cantidad":1,"Ancho":23,"Largo":21},
        {"Modelo":"MODELO-001","Talla":"L","Pieza":"SL","Cantidad":2,"Ancho":18,"Largo":11},])

def test_expansion_case_l():
    pieces=expand_pieces(library(),{"MODELO-001|L":2})
    counts={k:sum(p.piece==k for p in pieces) for k in ["FT","BK","SL"]}
    assert counts=={"FT":2,"BK":2,"SL":4}

def test_no_block_exceeds_width():
    pieces=expand_pieces(library(),{"MODELO-001|L":2})
    for _,blocks in build_distributions(pieces,72,5):
        assert all(b.used_width <= 72 for b in blocks)
        assert sum(b.length for b in blocks)>0

def test_reference_math():
    pieces=expand_pieces(library(),{"MODELO-001|L":2})
    assert sum(p.area for p in pieces)==2724
    assert round(2724/(72*53)*100,2)==71.38

def test_candidate_generation():
    req=pd.DataFrame([{"Modelo":"MODELO-001","Talla":"L","Unidades":100}])
    cs=generate_candidates(library(),req,72,50,50,random_iterations=5,max_candidates=10)
    assert cs
    assert all(c.production["MODELO-001|L"]==100 for c in cs)
