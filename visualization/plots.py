import plotly.graph_objects as go
def cut_figure(parsed):
 fig=go.Figure()
 for i,g in parsed["geometry"].items():
  pts=g["points"];fig.add_trace(go.Scatter(x=[x/parsed["diagnostic"]["Escala"] for x,y in pts],y=[y/parsed["diagnostic"]["Escala"] for x,y in pts],mode="lines",name=f"N{i}",hovertemplate=f"N{i}<extra></extra>"))
 fig.update_yaxes(scaleanchor="x",scaleratio=1);fig.update_layout(height=520,title="Geometrías del CUT",xaxis_title="X (pulgadas)",yaxis_title="Y (pulgadas)");return fig
def candidate_figure(c):
 fig=go.Figure();y=0;colors=['#2563eb','#16a34a','#ea580c','#7c3aed','#0891b2'];cm={}
 for b in c.blocks:
  x=0
  for p in b.pieces:
   k=p.model+'|'+p.size;cm.setdefault(k,colors[len(cm)%len(colors)])
   fig.add_shape(type='rect',x0=x,x1=x+p.width,y0=y,y1=y+b.length,fillcolor=cm[k],line=dict(color='white'))
   fig.add_annotation(x=x+p.width/2,y=y+b.length/2,text=f'{p.size}-{p.piece}',showarrow=False,font=dict(color='white',size=10));x+=p.width
  fig.add_shape(type='rect',x0=0,x1=b.fabric_width,y0=y,y1=y+b.length,line=dict(color='black',width=2),fillcolor='rgba(0,0,0,0)');y+=b.length+2
 fig.update_yaxes(autorange='reversed');fig.update_layout(height=max(420,int(y*8)),title=c.candidate_id);return fig
