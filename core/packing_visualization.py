"""Visualización horizontal del marcador, sin alterar coordenadas MaxRects.

En el motor: placement.x = ancho (transversal), placement.y = largo.
En el gráfico: eje X = largo horizontal, eje Y = ancho vertical.
"""
import plotly.graph_objects as go

PALETTE = ["#A02B93", "#2563EB", "#16A34A", "#EA580C", "#7C3AED", "#0891B2", "#DC2626"]


def packing_figure(result, title="Acomodación rectangular 2D"):
    sizes = list(dict.fromkeys(p.item.size for p in result.placements))
    colors = {size: PALETTE[i % len(PALETTE)] for i, size in enumerate(sizes)}
    fig = go.Figure()
    legend_seen = set()
    for placement in result.placements:
        item = placement.item
        # Se intercambian los ejes SOLO al dibujar. No se rota la pieza.
        x0, x1 = placement.y, placement.top      # longitud del marcador
        y0, y1 = placement.x, placement.right    # ancho de tela
        custom = [[item.model, item.size, item.piece,
                   placement.width, placement.length,
                   placement.x, placement.y]] * 5
        fig.add_trace(go.Scatter(
            x=[x0, x1, x1, x0, x0], y=[y0, y0, y1, y1, y0],
            mode="lines", fill="toself", fillcolor=colors[item.size],
            line=dict(color="white", width=1.5),
            name=f"Talla {item.size}", legendgroup=item.size,
            showlegend=item.size not in legend_seen, customdata=custom,
            hovertemplate=(
                "<b>%{customdata[0]} · %{customdata[1]} · %{customdata[2]}</b><br>"
                "Ancho: %{customdata[3]:.2f}<br>Largo: %{customdata[4]:.2f}<br>"
                "Coord. transversal: %{customdata[5]:.2f}<br>"
                "Coord. longitudinal: %{customdata[6]:.2f}<extra></extra>"
            ),
        ))
        legend_seen.add(item.size)
        if (placement.length >= result.used_length * 0.04
                and placement.width >= result.fabric_width * 0.12):
            fig.add_annotation(
                x=(x0 + x1) / 2, y=(y0 + y1) / 2,
                text=f"{item.piece} {item.size}", showarrow=False,
                font=dict(color="white", size=10),
            )
    fig.add_shape(type="rect", x0=0, x1=result.used_length,
                  y0=0, y1=result.fabric_width,
                  line=dict(color="#111827", width=2.5),
                  fillcolor="rgba(0,0,0,0)")
    fig.update_xaxes(title="Largo longitudinal del marcador →",
                     range=[0, max(result.used_length, 1e-8)],
                     constrain="domain", zeroline=False)
    fig.update_yaxes(title="Ancho transversal de tela",
                     range=[result.fabric_width, 0],
                     scaleanchor="x", scaleratio=1, zeroline=False)
    fig.update_layout(
        title=f"{title} | Largo {result.used_length:.2f} | Eficiencia rectangular {result.efficiency:.2%}",
        height=430,
        plot_bgcolor="#8B8B8B", paper_bgcolor="white",
        hovermode="closest", dragmode="pan",
        legend=dict(orientation="h", y=1.03, x=0),
        margin=dict(l=65, r=24, t=100, b=60),
    )
    return fig
