import pandas as pd
import streamlit as st
from core import generate_candidates, validate_inputs
from visualization import candidate_figure
from exports import candidates_to_excel

st.set_page_config(page_title="Predictor AccuMark / AccuNest", page_icon="📐", layout="wide")
st.title("Predictor de combinaciones AccuMark / AccuNest")
st.caption("Comparador rectangular predictivo. No sustituye el anidado geométrico de AccuNest.")

@st.cache_data
def examples():
    pieces=pd.read_csv("data/piezas_ejemplo.csv")
    req=pd.read_csv("data/requerimientos_ejemplo.csv")
    return pieces,req

def read_upload(upload):
    if upload.name.lower().endswith(".csv"):
        return pd.read_csv(upload,sep=None,engine="python")
    return pd.read_excel(upload,engine="openpyxl")

p0,r0=examples()
with st.sidebar:
    st.header("Configuración")
    width=st.number_input("Ancho de tela",min_value=0.01,value=72.0,step=0.5)
    c1,c2=st.columns(2)
    lmin=c1.number_input("Capas mín.",min_value=1,value=50)
    lmax=c2.number_input("Capas máx.",min_value=1,value=50)
    step=st.number_input("Incremento",min_value=1,value=1)
    max_over=st.number_input("Sobreproducción máxima (%)",min_value=0.0,value=25.0)
    allow_short=st.checkbox("Permitir faltante temporal",value=True)
    random_n=st.slider("Iteraciones aleatorias",0,100,20)
    max_candidates=st.slider("Máximo de candidatos",10,500,100,10)
    st.subheader("Pesos del ranking")
    wg=st.slider("Geométrico",0.0,1.0,0.40,0.05)
    wc=st.slider("Cumplimiento",0.0,1.0,0.30,0.05)
    wo=st.slider("Baja sobreproducción",0.0,1.0,0.15,0.05)
    wop=st.slider("Operabilidad",0.0,1.0,0.15,0.05)

st.subheader("1. Datos de entrada")
a,b=st.columns(2)
with a:
    up_p=st.file_uploader("Biblioteca de piezas (CSV/XLSX)",type=["csv","xlsx"],key="p")
    try: pieces=read_upload(up_p) if up_p else p0.copy()
    except Exception as e: st.error(f"No se pudo leer la biblioteca: {e}"); pieces=p0.copy()
    pieces=st.data_editor(pieces,num_rows="dynamic",use_container_width=True,key="pieces")
with b:
    up_r=st.file_uploader("Requerimientos (CSV/XLSX)",type=["csv","xlsx"],key="r")
    try: req=read_upload(up_r) if up_r else r0.copy()
    except Exception as e: st.error(f"No se pudo leer el requerimiento: {e}"); req=r0.copy()
    req=st.data_editor(req,num_rows="dynamic",use_container_width=True,key="req")

if st.button("Generar candidatos",type="primary",use_container_width=True):
    errors,warnings=validate_inputs(pieces,req)
    for w in warnings: st.warning(w)
    if errors:
        for e in errors: st.error(e)
    else:
        weights={"geometry":wg,"compliance":wc,"low_over":wo,"operability":wop}
        total=sum(weights.values())
        if total<=0: st.error("La suma de pesos debe ser mayor que cero.")
        else:
            weights={k:v/total for k,v in weights.items()}
            try:
                st.session_state.candidates=generate_candidates(pieces,req,width,lmin,lmax,step,max_over,allow_short,random_n,max_candidates,weights)
                st.session_state.params={"AnchoTela":width,"CapasMin":lmin,"CapasMax":lmax,"Incremento":step,"SobreproduccionMaxPct":max_over,"IteracionesAleatorias":random_n,**weights}
            except Exception as e: st.error(f"No fue posible generar candidatos: {e}")

cs=st.session_state.get("candidates",[])
if cs:
    st.subheader("2. Ranking de candidatos")
    rows=[]
    for c in cs:
        rows.append({"Candidato":c.candidate_id,"Capas":c.layers,"Estrategia":c.strategy,"Repeticiones":", ".join(f"{k}={v}" for k,v in c.repetitions.items()),"Bloques":len(c.blocks),"Piezas":sum(len(x.pieces) for x in c.blocks),"Largo":c.estimated_length,"Eficiencia %":100*c.rectangular_efficiency,"Cumplimiento %":100*c.demand_compliance,"Puntaje":c.total_score})
    ranking=pd.DataFrame(rows)
    st.dataframe(ranking,hide_index=True,use_container_width=True,column_config={"Eficiencia %":st.column_config.NumberColumn(format="%.2f%%"),"Cumplimiento %":st.column_config.NumberColumn(format="%.2f%%"),"Puntaje":st.column_config.NumberColumn(format="%.2f")})
    selected=st.selectbox("Candidato para inspeccionar",[c.candidate_id for c in cs])
    c=next(x for x in cs if x.candidate_id==selected)
    m1,m2,m3,m4=st.columns(4)
    m1.metric("Largo estimado",f"{c.estimated_length:.2f}")
    m2.metric("Eficiencia rectangular",f"{c.rectangular_efficiency:.2%}")
    m3.metric("Bloques",len(c.blocks))
    m4.metric("Puntuación",f"{c.total_score:.2f}")
    st.plotly_chart(candidate_figure(c),use_container_width=True)
    block_rows=[{"Bloque":b.number,"Ancho usado":b.used_width,"Libre":b.free_width,"Largo":b.length,"Piezas":", ".join(p.uid for p in b.pieces)} for b in c.blocks]
    st.dataframe(pd.DataFrame(block_rows),hide_index=True,use_container_width=True)
    excel=candidates_to_excel(cs,st.session_state.params)
    st.download_button("Descargar resultados en Excel",excel,"resultados_predictor_accunest.xlsx","application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",use_container_width=True)
else:
    st.info("Revise los datos y pulse “Generar candidatos”. Los ejemplos precargados reproducen el caso obligatorio de talla L.")
