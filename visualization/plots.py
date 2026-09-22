import plotly.graph_objects as go
from plotly.subplots import make_subplots


PALETTE = [
    "#2563EB",  # azul
    "#16A34A",  # verde
    "#EA580C",  # naranja
    "#7C3AED",  # violeta
    "#0891B2",  # turquesa
    "#DC2626",  # rojo
    "#CA8A04",  # amarillo oscuro
    "#DB2777",  # rosa
]


def _safe_number(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def cut_figure(parsed):
    """Visualiza los contornos reales detectados en un CUT/TXT."""
    fig = go.Figure()
    scale = _safe_number(parsed.get("diagnostic", {}).get("Escala"), 100.0) or 100.0
    instances = parsed.get("instances")

    metadata = {}
    if instances is not None and not instances.empty:
        for _, row in instances.iterrows():
            metadata[int(row["ID"])] = row.to_dict()

    all_x = []
    all_y = []

    for geometry_id, geometry in parsed.get("geometry", {}).items():
        points = geometry.get("points", [])
        if not points:
            continue

        x_values = [x / scale for x, _ in points]
        y_values = [y / scale for _, y in points]
        all_x.extend(x_values)
        all_y.extend(y_values)

        item = metadata.get(int(geometry_id), {})
        model = item.get("Modelo", "")
        size = item.get("Talla", "")
        piece = item.get("Pieza", "")
        side = item.get("Lado", "")
        width = _safe_number(item.get("Ancho", geometry.get("width")))
        length = _safe_number(item.get("Largo", geometry.get("length")))

        descriptive_name = " · ".join(
            part for part in [f"N{geometry_id}", str(size), str(piece)] if part
        )
        hover = (
            f"<b>{descriptive_name}</b><br>"
            f"Modelo: {model}<br>"
            f"Talla: {size}<br>"
            f"Pieza: {piece}<br>"
            f"Lado: {side}<br>"
            f"Ancho envolvente: {width:.2f} in<br>"
            f"Largo envolvente: {length:.2f} in"
            "<extra></extra>"
        )

        fig.add_trace(
            go.Scatter(
                x=x_values,
                y=y_values,
                mode="lines",
                name=descriptive_name,
                hovertemplate=hover,
                line=dict(width=2),
            )
        )

    if all_x and all_y:
        x_span = max(all_x) - min(all_x)
        y_span = max(all_y) - min(all_y)
        x_margin = max(x_span * 0.03, 1.0)
        y_margin = max(y_span * 0.03, 1.0)
        fig.update_xaxes(range=[min(all_x) - x_margin, max(all_x) + x_margin])
        fig.update_yaxes(range=[min(all_y) - y_margin, max(all_y) + y_margin])

    fig.update_yaxes(scaleanchor="x", scaleratio=1)
    fig.update_layout(
        height=560,
        title="Geometrías del CUT",
        xaxis_title="X (pulgadas)",
        yaxis_title="Y (pulgadas)",
        hovermode="closest",
        legend=dict(
            orientation="v",
            yanchor="top",
            y=1,
            xanchor="left",
            x=1.01,
            font=dict(size=10),
        ),
        margin=dict(l=50, r=170, t=60, b=50),
        dragmode="pan",
    )
    return fig


def candidate_figure(candidate):
    """
    Visualiza cada bloque como una fila compacta.

    El ancho mantiene la proporción real respecto al ancho de tela. La altura de
    cada fila es fija para evitar que un marcador largo produzca una gráfica
    excesivamente alta. El largo real de cada bloque se conserva como etiqueta
    y en la información emergente.
    """
    blocks = candidate.blocks or []
    if not blocks:
        fig = go.Figure()
        fig.add_annotation(
            text="El candidato no contiene bloques para visualizar.",
            x=0.5,
            y=0.5,
            xref="paper",
            yref="paper",
            showarrow=False,
        )
        fig.update_layout(height=320)
        return fig

    fabric_width = max(_safe_number(block.fabric_width) for block in blocks)
    row_height = 0.72
    candidate_height = min(max(440, 105 + len(blocks) * 54), 1050)

    size_order = []
    for block in blocks:
        for piece in block.pieces:
            if piece.size not in size_order:
                size_order.append(piece.size)
    color_by_size = {
        size: PALETTE[index % len(PALETTE)]
        for index, size in enumerate(size_order)
    }

    fig = go.Figure()
    legend_added = set()

    for visual_row, block in enumerate(blocks):
        y_center = len(blocks) - visual_row
        y0 = y_center - row_height / 2
        y1 = y_center + row_height / 2
        current_x = 0.0

        for piece in block.pieces:
            piece_width = _safe_number(piece.width)
            piece_length = _safe_number(piece.length)
            x0 = current_x
            x1 = current_x + piece_width
            color = color_by_size.get(piece.size, "#64748B")
            show_legend = piece.size not in legend_added
            legend_added.add(piece.size)

            custom = [[
                block.number,
                piece.model,
                piece.size,
                piece.piece,
                piece_width,
                piece_length,
                _safe_number(block.length),
            ]] * 5

            fig.add_trace(
                go.Scatter(
                    x=[x0, x1, x1, x0, x0],
                    y=[y0, y0, y1, y1, y0],
                    mode="lines",
                    fill="toself",
                    fillcolor=color,
                    line=dict(color="white", width=1.5),
                    name=f"Talla {piece.size}",
                    legendgroup=f"size-{piece.size}",
                    showlegend=show_legend,
                    customdata=custom,
                    hovertemplate=(
                        "<b>Bloque %{customdata[0]}</b><br>"
                        "Modelo: %{customdata[1]}<br>"
                        "Talla: %{customdata[2]}<br>"
                        "Pieza: %{customdata[3]}<br>"
                        "Ancho: %{customdata[4]:.2f}<br>"
                        "Largo de pieza: %{customdata[5]:.2f}<br>"
                        "Largo del bloque: %{customdata[6]:.2f}"
                        "<extra></extra>"
                    ),
                )
            )

            label = f"{piece.size}-{piece.piece}"
            if piece_width >= fabric_width * 0.105:
                fig.add_annotation(
                    x=(x0 + x1) / 2,
                    y=y_center,
                    text=label,
                    showarrow=False,
                    font=dict(color="white", size=10),
                )
            current_x = x1

        free_width = max(0.0, fabric_width - current_x)
        if free_width > 0.001:
            custom_free = [[block.number, free_width, _safe_number(block.length)]] * 5
            fig.add_trace(
                go.Scatter(
                    x=[current_x, fabric_width, fabric_width, current_x, current_x],
                    y=[y0, y0, y1, y1, y0],
                    mode="lines",
                    fill="toself",
                    fillcolor="#E5E7EB",
                    line=dict(color="#CBD5E1", width=1),
                    name="Espacio libre",
                    legendgroup="free-space",
                    showlegend=visual_row == 0,
                    customdata=custom_free,
                    hovertemplate=(
                        "<b>Espacio libre</b><br>"
                        "Bloque: %{customdata[0]}<br>"
                        "Ancho libre: %{customdata[1]:.2f}<br>"
                        "Largo del bloque: %{customdata[2]:.2f}"
                        "<extra></extra>"
                    ),
                )
            )

        fig.add_shape(
            type="rect",
            x0=0,
            x1=fabric_width,
            y0=y0,
            y1=y1,
            line=dict(color="#111827", width=1.4),
            fillcolor="rgba(0,0,0,0)",
            layer="above",
        )

        fig.add_annotation(
            x=fabric_width + fabric_width * 0.015,
            y=y_center,
            text=(
                f"L={_safe_number(block.length):.2f} | "
                f"Usado={_safe_number(block.used_width):.2f} | "
                f"Libre={_safe_number(block.free_width):.2f}"
            ),
            showarrow=False,
            xanchor="left",
            font=dict(size=10, color="#374151"),
        )

    total_pieces = sum(len(block.pieces) for block in blocks)
    total_length = _safe_number(candidate.estimated_length)
    efficiency = _safe_number(candidate.rectangular_efficiency) * 100
    compliance = _safe_number(candidate.demand_compliance) * 100

    fig.update_xaxes(
        title="Ancho de tela",
        range=[0, fabric_width * 1.30],
        fixedrange=False,
        showgrid=True,
        gridcolor="#E5E7EB",
        zeroline=False,
    )
    fig.update_yaxes(
        title="Bloque",
        tickmode="array",
        tickvals=list(range(1, len(blocks) + 1)),
        ticktext=[f"B{block.number}" for block in reversed(blocks)],
        range=[0.35, len(blocks) + 0.65],
        fixedrange=False,
        showgrid=False,
        zeroline=False,
    )
    fig.update_layout(
        height=candidate_height,
        title=(
            f"{candidate.candidate_id} | "
            f"{len(blocks)} bloques | {total_pieces} piezas | "
            f"Largo total {total_length:.2f} | "
            f"Eficiencia {efficiency:.2f}% | "
            f"Cumplimiento {compliance:.2f}%"
        ),
        hovermode="closest",
        dragmode="pan",
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0,
            font=dict(size=10),
        ),
        margin=dict(l=65, r=245, t=105, b=55),
        plot_bgcolor="white",
        paper_bgcolor="white",
    )
    return fig
