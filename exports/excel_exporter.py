from io import BytesIO
import pandas as pd

def _key_parts(key):
    return key.split("|",1) if "|" in key else ("",key)

def candidates_to_excel(candidates, parameters):
    out=BytesIO(); summaries=[]; prod=[]; blocks=[]; pieces=[]
    for c in candidates:
        summaries.append({"Candidato":c.candidate_id,"Capas":c.layers,"Estrategia":c.strategy,"Piezas":sum(len(b.pieces) for b in c.blocks),"Bloques":len(c.blocks),"LargoEstimado":c.estimated_length,"EficienciaRectangular":c.rectangular_efficiency,"Cumplimiento":c.demand_compliance,"Puntuacion":c.total_score})
        for key, made in c.production.items():
            model,size=_key_parts(key); prod.append({"Candidato":c.candidate_id,"Modelo":model,"Talla":size,"Repeticiones":c.repetitions[key],"Producido":made,"Faltante":c.shortages[key],"Sobreproduccion":c.overproduction[key]})
        for b in c.blocks:
            blocks.append({"Candidato":c.candidate_id,"Bloque":b.number,"AnchoTela":b.fabric_width,"AnchoUsado":b.used_width,"AnchoLibre":b.free_width,"Largo":b.length,"Contenido":", ".join(p.uid for p in b.pieces)})
            for p in b.pieces:
                pieces.append({"Candidato":c.candidate_id,"Bloque":b.number,"IDPieza":p.uid,"Modelo":p.model,"Talla":p.size,"Pieza":p.piece,"Ancho":p.width,"Largo":p.length,"Area":p.area})
    with pd.ExcelWriter(out,engine="openpyxl") as w:
        pd.DataFrame(summaries).to_excel(w,index=False,sheet_name="Candidatos")
        pd.DataFrame(prod).to_excel(w,index=False,sheet_name="Produccion")
        pd.DataFrame(blocks).to_excel(w,index=False,sheet_name="Bloques")
        pd.DataFrame(pieces).to_excel(w,index=False,sheet_name="Piezas")
        pd.DataFrame([parameters]).to_excel(w,index=False,sheet_name="Parametros")
        pd.DataFrame(columns=["Candidato","LargoRealAccuNest","EficienciaReal","TiempoAnidado","Observaciones"]).to_excel(w,index=False,sheet_name="Resultado_AccuNest")
    out.seek(0); return out.getvalue()
