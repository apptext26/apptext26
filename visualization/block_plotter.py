import plotly.graph_objects as go

def candidate_figure(candidate):
    fig=go.Figure(); y=0.0; max_width=max((b.fabric_width for b in candidate.blocks), default=1)
    palette=["#2563eb","#16a34a","#ea580c","#7c3aed","#0891b2","#dc2626"]
    color_map={}
    for block in candidate.blocks:
        x=0.0
        for p in block.pieces:
            key=f"{p.model}|{p.size}"
            if key not in color_map: color_map[key]=palette[len(color_map)%len(palette)]
            fig.add_shape(type="rect",x0=x,x1=x+p.width,y0=y,y1=y+block.length,
                          line=dict(color="white",width=1),fillcolor=color_map[key])
            fig.add_annotation(x=x+p.width/2,y=y+block.length/2,
                               text=f"{p.size}-{p.piece}<br>{p.width:g}×{p.length:g}",showarrow=False,font=dict(size=10,color="white"))
            x+=p.width
        fig.add_shape(type="rect",x0=0,x1=max_width,y0=y,y1=y+block.length,line=dict(color="#111827",width=2),fillcolor="rgba(0,0,0,0)")
        fig.add_annotation(x=max_width+1,y=y+block.length/2,text=f"B{block.number}: L={block.length:g}",showarrow=False,xanchor="left")
        y+=block.length+2
    fig.update_xaxes(title="Ancho",range=[0,max_width*1.18],scaleanchor="y",scaleratio=1)
    fig.update_yaxes(title="Secuencia de bloques",autorange="reversed")
    fig.update_layout(height=max(420,int(y*9)),margin=dict(l=20,r=90,t=40,b=40),showlegend=False,title=f"{candidate.candidate_id} | {candidate.strategy}")
    return fig
