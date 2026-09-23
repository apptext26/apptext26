import plotly.graph_objects as go

PALETTE = ["#A02B93", "#2563EB", "#16A34A", "#EA580C", "#7C3AED", "#0891B2", "#DC2626"]


def packing_figure(result, title="Acomodación rectangular 2D"):
    sizes = []
    for placement in result.placements:
        if placement.item.size not in sizes:
            sizes.append(placement.item.size)
    colors = {size: PALETTE[index % len(PALETTE)] for index, size in enumerate(sizes)}

    fig = go.Figure()
    legend_seen = set()
    for placement in result.placements:
        item = placement.item
        x0, x1 = placement.x, placement.right
        y0, y1 = placement.y, placement.top
        custom = [[item.model, item.size, item.piece, placement.width, placement.length, placement.x, placement.y]] * 5
        fig.add_trace(go.Scatter(
            x=[x0, x1, x1, x0, x0],
            y=[y0, y0, y1, y1, y0],
            mode="lines",
            fill="toself",
            fillcolor=colors[item.size],
            line=dict(color="white", width=2),
            name=f"Talla {item.size}",
            legendgroup=item.size,
            showlegend=item.size not in legend_seen,
            customdata=custom,
            hovertemplate=(
                "<b>%{customdata[0]} · %{customdata[1]} · %{customdata[2]}</b><br>"
                "Ancho: %{customdata[3]:.2f}<br>Largo: %{customdata[4]:.2f}<br>"
                "X: %{customdata[5]:.2f}<br>Y: %{customdata[6]:.2f}<extra></extra>"
            ),
        ))
        legend_seen.add(item.size)
        if placement.width >= result.fabric_width * 0.12 and placement.length >= result.used_length * 0.04:
            fig.add_annotation(
                x=(x0 + x1) / 2,
                y=(y0 + y1) / 2,
                text=f"{item.piece} {item.size}",
                showarrow=False,
                font=dict(color="white", size=11),
            )

    fig.add_shape(
        type="rect", x0=0, x1=result.fabric_width, y0=0, y1=result.used_length,
        line=dict(color="#111827", width=3), fillcolor="rgba(0,0,0,0)",
    )
    fig.update_xaxes(title="Ancho de tela", range=[0, result.fabric_width], constrain="domain")
    fig.update_yaxes(title="Largo del marcador", range=[result.used_length, 0], scaleanchor="x", scaleratio=1)
    fig.update_layout(
        title=f"{title} | Largo {result.used_length:.2f} | Eficiencia {result.efficiency:.2%}",
        height=max(520, min(1100, int(180 + result.used_length * 4))),
        plot_bgcolor="#8B8B8B",
        paper_bgcolor="white",
        hovermode="closest",
        dragmode="pan",
        legend=dict(orientation="h", y=1.02, x=0),
        margin=dict(l=55, r=30, t=90, b=55),
    )
    return fig
