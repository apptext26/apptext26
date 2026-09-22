import pandas as pd
import streamlit as st
from core import parse_cut,normalize_library,generate,validate
from visualization import cut_figure,candidate_figure
from exports import library_excel
st.set_page_config(page_title="Predictor AccuMark / AccuNest",page_icon="📐",layout="wide")
st.title("Predictor de combinaciones AccuMark / AccuNest")
st.caption("Analiza CUT/TXT, construye una biblioteca rectangular y compara candidatos. No sustituye AccuNest.")
if 'library' not in st.session_state:st.session_state.library=pd.read_csv('data/piezas_ejemplo.csv')
if 'req' not in st.session_state:st.session_state.req=pd.read_csv('data/requerimientos_ejemplo.csv')
tab1,tab2,tab3=st.tabs(["1. Analizador CUT/TXT","2. Predictor","3. Metodología"])
with tab1:
 files=st.file_uploader("Cargue uno o varios CUT/TXT",type=['cut','txt'],accept_multiple_files=True)
 if files:
  parsed=[parse_cut(f.getvalue(),f.name) for f in files];st.session_state.parsed=parsed
 if st.session_state.get('parsed'):
  parsed=st.session_state.parsed
  diag=pd.DataFrame([p['diagnostic'] for p in parsed]);st.subheader('Diagnóstico');st.dataframe(diag,hide_index=True,use_container_width=True)
  combined=pd.concat([p['library'] for p in parsed],ignore_index=True)
  # Merge exact model/size/piece across files conservatively.
  combined=combined.groupby(['Modelo','Talla','Pieza'],as_index=False).agg(InstanciasCUT=('InstanciasCUT','max'),RepeticionesTalla=('RepeticionesTalla','max'),Cantidad=('Cantidad','max'),Ancho=('Ancho','max'),Largo=('Largo','max'),Unidad=('Unidad','first'),Confianza=('Confianza','min'))
  st.info('InstanciasCUT es lo encontrado en el marcador. Ajuste RepeticionesTalla si el CUT contiene más de una repetición de una talla.')
  edited=st.data_editor(combined,num_rows='dynamic',use_container_width=True,key='cutlib')
  normalized=normalize_library(edited);st.subheader('Biblioteca normalizada');st.dataframe(normalized,hide_index=True,use_container_width=True)
  c1,c2=st.columns(2)
  if c1.button('Usar biblioteca detectada',type='primary',use_container_width=True):st.session_state.library=normalized.drop(columns=['Unidad','Confianza']);st.success('Biblioteca enviada al predictor.')
  c2.download_button('Descargar biblioteca y diagnóstico',library_excel(normalized,diag),'biblioteca_cut.xlsx',use_container_width=True)
  pick=st.selectbox('Archivo para visualizar',[p['diagnostic']['Archivo'] for p in parsed]);pp=next(p for p in parsed if p['diagnostic']['Archivo']==pick);st.plotly_chart(cut_figure(pp),use_container_width=True)
with tab2:
 with st.sidebar:
  st.header('Configuración');width=st.number_input('Ancho de tela',0.01,value=80.0);a,b=st.columns(2);lmin=a.number_input('Capas mín.',1,value=50);lmax=b.number_input('Capas máx.',1,value=50);step=st.number_input('Incremento',1,value=1);maxover=st.number_input('Sobreproducción máxima (%)',0.0,value=25.0);short=st.checkbox('Permitir faltante temporal',True);rn=st.slider('Iteraciones aleatorias',0,100,20);maxn=st.slider('Máximo de candidatos',10,500,100,10)
  st.subheader('Pesos');wg=st.slider('Geométrico',0.,1.,.4,.05);wc=st.slider('Cumplimiento',0.,1.,.3,.05);wo=st.slider('Baja sobreproducción',0.,1.,.15,.05);wp=st.slider('Operabilidad',0.,1.,.15,.05)
 st.subheader('Datos de entrada');x,y=st.columns(2)
 with x:lib=st.data_editor(st.session_state.library,num_rows='dynamic',use_container_width=True,key='libedit')
 with y:req=st.data_editor(st.session_state.req,num_rows='dynamic',use_container_width=True,key='reqedit')
 if st.button('Generar candidatos',type='primary',use_container_width=True):
  es=validate(lib,req)
  if es:[st.error(e) for e in es]
  else:
   s=wg+wc+wo+wp;w={'g':wg/s,'c':wc/s,'o':wo/s,'p':wp/s};st.session_state.cs,st.session_state.stats=generate(lib,req,width,lmin,lmax,step,maxover,short,rn,maxn,w)
 cs=st.session_state.get('cs',[])
 if cs:
  q=st.session_state.stats;c1,c2,c3=st.columns(3);c1.metric('Evaluados',q['evaluados']);c2.metric('Distribuciones únicas',q['unicos']);c3.metric('Duplicados agrupados',q['duplicados'])
  rows=[]
  for c in cs:rows.append({'Candidato':c.candidate_id,'Capas':c.layers,'Estrategia principal':c.strategy,'Estrategias equivalentes':len(c.equivalent_strategies),'Bloques':len(c.blocks),'Piezas':sum(len(b.pieces) for b in c.blocks),'Largo':c.estimated_length,'Eficiencia %':100*c.rectangular_efficiency,'Cumplimiento %':100*c.demand_compliance,'Puntaje':c.total_score})
  st.dataframe(pd.DataFrame(rows),hide_index=True,use_container_width=True)
  sid=st.selectbox('Inspeccionar',[c.candidate_id for c in cs]);c=next(z for z in cs if z.candidate_id==sid)
  if c.equivalent_strategies:st.caption('Estrategias equivalentes agrupadas: '+', '.join(c.equivalent_strategies))
  st.plotly_chart(candidate_figure(c),use_container_width=True)
with tab3:
 st.markdown("""### Reglas aplicadas\n- Las coordenadas se leen directamente del CUT/TXT.\n- La escala se contrasta con el ancho declarado del marcador.\n- Las dimensiones son rectángulos envolventes según la orientación del marcador.\n- En piezas izquierda/derecha se conserva la dimensión máxima para evitar subestimar.\n- **Instancias CUT** y **cantidad por prenda** se mantienen separadas.\n- Los candidatos equivalentes se agrupan por contenido exacto de bloques, capas y repeticiones.""")
