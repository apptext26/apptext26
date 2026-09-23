import pandas as pd
import streamlit as st

from core.cut_parser import LibraryNormalizationError, normalize_library, parse_cut
from core.cut_library import consolidate_cut_libraries
from core.layer_optimizer import evaluate_layer_range
from core.packing_visualization import packing_figure
from core.plan_optimizer import PlanGenerationError, generate_marker_plan, marker_summary
from core.validation import validate
from exports import library_excel
from visualization import cut_figure


st.set_page_config(
    page_title="Predictor AccuMark / AccuNest",
    page_icon="📐",
    layout="wide",
)

st.title("Predictor de combinaciones AccuMark / AccuNest")
st.caption(
    "Analiza CUT/TXT, evalúa un rango de capas y propone una lista corta "
    "de marcadores mediante packing rectangular 2D."
)


@st.cache_data
def load_examples():
    library = pd.read_csv("data/piezas_ejemplo.csv")
    requirements = pd.read_csv("data/requerimientos_ejemplo.csv")
    return library, requirements


if "library" not in st.session_state or "requirements" not in st.session_state:
    default_library, default_requirements = load_examples()
    st.session_state.setdefault("library", default_library)
    st.session_state.setdefault("requirements", default_requirements)


def clear_calculation_results():
    st.session_state.pop("layer_alternatives", None)
    st.session_state.pop("selected_plan_id", None)
    st.session_state.pop("selected_marker_id", None)


def format_repetitions(repetitions):
    parts = []
    for key, quantity in sorted(repetitions.items()):
        model, size = key.split("|", 1) if "|" in key else ("", key)
        parts.append(f"{model} {size} x {quantity}".strip())
    return ", ".join(parts)


def marker_piece_audit(library, marker):
    expected = {}
    for _, row in library.iterrows():
        repetition_key = f"{row['Modelo']}|{row['Talla']}"
        repetitions = int(marker.repetitions.get(repetition_key, 0))
        if repetitions <= 0:
            continue

        piece_key = (
            str(row["Modelo"]),
            str(row["Talla"]),
            str(row["Pieza"]),
        )
        expected[piece_key] = repetitions * int(row["Cantidad"])

    actual = {}
    for placement in marker.packing.placements:
        item = placement.item
        piece_key = (str(item.model), str(item.size), str(item.piece))
        actual[piece_key] = actual.get(piece_key, 0) + 1

    rows = []
    for piece_key in sorted(set(expected) | set(actual)):
        wanted = expected.get(piece_key, 0)
        found = actual.get(piece_key, 0)
        rows.append(
            {
                "Modelo": piece_key[0],
                "Talla": piece_key[1],
                "Pieza": piece_key[2],
                "Esperado": wanted,
                "Encontrado": found,
                "Estado": "Completo" if wanted == found else "Revisar",
            }
        )
    return pd.DataFrame(rows)


def placement_table(marker):
    rows = []
    for placement in marker.packing.placements:
        item = placement.item
        rows.append(
            {
                "ID": item.uid,
                "Modelo": item.model,
                "Talla": item.size,
                "Pieza": item.piece,
                "X": placement.x,
                "Y": placement.y,
                "Ancho": placement.width,
                "Largo": placement.length,
                "X final": placement.right,
                "Y final": placement.top,
            }
        )
    return pd.DataFrame(rows)


tab_cut, tab_plan, tab_method = st.tabs(
    [
        "1. Analizador CUT/TXT",
        "2. Planes y acomodaciones 2D",
        "3. Metodología",
    ]
)


with tab_cut:
    uploads = st.file_uploader(
        "Cargue uno o varios archivos CUT/TXT",
        type=["cut", "txt"],
        accept_multiple_files=True,
    )

    if uploads:
        upload_signature = tuple(
            (upload.name, len(upload.getvalue())) for upload in uploads
        )
        if st.session_state.get("upload_signature") != upload_signature:
            st.session_state.parsed_cut = [
                parse_cut(upload.getvalue(), upload.name)
                for upload in uploads
            ]
            st.session_state.upload_signature = upload_signature
            clear_calculation_results()

    parsed_files = st.session_state.get("parsed_cut", [])

    if parsed_files:
        diagnostics = pd.DataFrame(
            [parsed["diagnostic"] for parsed in parsed_files]
        )
        st.subheader("Diagnóstico")
        st.dataframe(diagnostics, hide_index=True, use_container_width=True)

        detected, consolidation_conflicts = consolidate_cut_libraries(
            parsed_files
        )

        st.info(
            "Ancho corresponde al eje transversal de la tela y Largo a la "
            "dirección longitudinal del marcador. Ajuste RepeticionesTalla "
            "cuando el CUT contenga más de una repetición."
        )

        detected_edited = st.data_editor(
            detected,
            num_rows="dynamic",
            use_container_width=True,
            key="detected_library_editor",
            disabled=[
                "Modelo",
                "Talla",
                "Pieza",
                "InstanciasCUT",
                "Origenes",
                "IDRepresentante",
                "DimensionStatus",
            ],
            column_config={
                "ConflictoCritico": st.column_config.CheckboxColumn(
                    "Conflicto crítico",
                    help=(
                        "Desmarque solamente después de revisar y corregir "
                        "manualmente dimensiones y conteos."
                    ),
                ),
                "RepeticionesTalla": st.column_config.NumberColumn(
                    "Repeticiones talla",
                    min_value=1,
                    step=1,
                    format="%d",
                ),
                "Ancho": st.column_config.NumberColumn(
                    "Ancho transversal",
                    min_value=0.0001,
                    format="%.4f",
                ),
                "Largo": st.column_config.NumberColumn(
                    "Largo longitudinal",
                    min_value=0.0001,
                    format="%.4f",
                ),
            },
        )

        if not consolidation_conflicts.empty:
            st.error(
                "Existen conflictos críticos entre los CUT cargados. "
                "Revise archivo, modelo, talla, pieza y dimensiones."
            )
            st.dataframe(
                consolidation_conflicts,
                hide_index=True,
                use_container_width=True,
            )

        normalized = None
        normalization_errors = pd.DataFrame()
        try:
            normalized = normalize_library(detected_edited)
        except LibraryNormalizationError as error:
            normalization_errors = error.to_frame()
            st.error(
                "La biblioteca no es válida todavía. Corrija las repeticiones, "
                "dimensiones o conflictos indicados."
            )
            st.dataframe(
                normalization_errors,
                hide_index=True,
                use_container_width=True,
            )

        st.subheader("Biblioteca normalizada")
        if normalized is not None:
            st.dataframe(normalized, hide_index=True, use_container_width=True)
        else:
            st.caption("No disponible hasta resolver todos los errores críticos.")

        unresolved_conflicts = bool(
            detected_edited.get(
                "ConflictoCritico",
                pd.Series(False, index=detected_edited.index),
            )
            .fillna(False)
            .astype(bool)
            .any()
        )

        can_use_library = (
            normalized is not None
            and consolidation_conflicts.empty
            and normalization_errors.empty
            and not unresolved_conflicts
        )

        left, right = st.columns(2)
        if left.button(
            "Usar biblioteca detectada",
            type="primary",
            use_container_width=True,
            disabled=not can_use_library,
        ):
            st.session_state.library = normalized.drop(
                columns=["Unidad", "Confianza"],
                errors="ignore",
            )
            clear_calculation_results()
            st.success("Biblioteca enviada al optimizador de planes.")

        if can_use_library:
            right.download_button(
                "Descargar biblioteca y diagnóstico",
                library_excel(normalized, diagnostics),
                "biblioteca_cut.xlsx",
                use_container_width=True,
            )
        else:
            right.button(
                "Descargar biblioteca y diagnóstico",
                disabled=True,
                use_container_width=True,
                help="Resuelva primero todos los conflictos y errores.",
            )

        selected_filename = st.selectbox(
            "Archivo para visualizar",
            [parsed["diagnostic"]["Archivo"] for parsed in parsed_files],
        )
        selected_parsed = next(
            parsed
            for parsed in parsed_files
            if parsed["diagnostic"]["Archivo"] == selected_filename
        )
        st.plotly_chart(cut_figure(selected_parsed), use_container_width=True)
    else:
        st.info("Cargue un CUT/TXT para construir la biblioteca.")


with tab_plan:
    with st.sidebar:
        st.header("Configuración del plan")

        fabric_width = st.number_input(
            "Ancho útil de tela",
            min_value=0.01,
            value=72.0,
            step=0.5,
        )

        st.subheader("Rango de capas")
        layer_col_1, layer_col_2 = st.columns(2)
        layers_min = layer_col_1.number_input(
            "Capas mínimas",
            min_value=1,
            value=40,
            step=1,
        )
        layers_max = layer_col_2.number_input(
            "Capas máximas",
            min_value=1,
            value=60,
            step=1,
        )
        layer_step = st.number_input(
            "Incremento de capas",
            min_value=1,
            value=1,
            step=1,
        )
        top_k_plans = st.number_input(
            "Planes a conservar",
            min_value=1,
            max_value=10,
            value=5,
            step=1,
        )

        st.subheader("Límites por marcador")
        max_marker_length = st.number_input(
            "Largo máximo por marcador",
            min_value=1.0,
            value=500.0,
            step=10.0,
        )
        target_length_input = st.number_input(
            "Largo objetivo por marcador",
            min_value=1.0,
            value=450.0,
            step=10.0,
        )
        target_marker_length = min(
            float(target_length_input),
            float(max_marker_length),
        )
        if target_length_input > max_marker_length:
            st.warning(
                "El objetivo supera el máximo. Se utilizará "
                f"{target_marker_length:.2f}."
            )

        max_distinct_sizes = st.number_input(
            "Máximo de tallas diferentes",
            min_value=1,
            value=3,
            step=1,
        )
        max_markers = st.number_input(
            "Máximo de marcadores del plan",
            min_value=1,
            value=20,
            step=1,
        )

        st.subheader("Búsqueda 2D")
        random_iterations = st.slider(
            "Órdenes aleatorios por propuesta",
            min_value=0,
            max_value=40,
            value=8,
        )
        allow_overproduction = st.checkbox(
            "Completar divisiones no enteras con sobreproducción",
            value=True,
        )

    valid_layer_range = layers_min <= layers_max
    if not valid_layer_range:
        st.error("Capas mínimas no puede ser mayor que Capas máximas.")

    st.subheader("Datos de entrada")
    left, right = st.columns(2)
    with left:
        st.caption("Biblioteca de piezas")
        library = st.data_editor(
            st.session_state.library,
            num_rows="dynamic",
            use_container_width=True,
            key="plan_library_editor",
        )
    with right:
        st.caption("Requerimientos")
        requirements = st.data_editor(
            st.session_state.requirements,
            num_rows="dynamic",
            use_container_width=True,
            key="plan_requirements_editor",
        )

    st.session_state.library = library
    st.session_state.requirements = requirements

    generate_clicked = st.button(
        "Calcular planes y acomodaciones 2D",
        type="primary",
        use_container_width=True,
        disabled=not valid_layer_range,
    )

    if generate_clicked:
        input_errors = validate(library, requirements)
        if input_errors:
            for error in input_errors:
                st.error(error)
        else:
            try:
                total_layer_values = (
                    (int(layers_max) - int(layers_min)) // int(layer_step)
                ) + 1
                with st.spinner(
                    f"Evaluando {total_layer_values} cantidades de capas y "
                    "múltiples acomodaciones MaxRects..."
                ):
                    st.session_state.layer_alternatives = evaluate_layer_range(
                        plan_factory=generate_marker_plan,
                        layers_min=int(layers_min),
                        layers_max=int(layers_max),
                        layer_step=int(layer_step),
                        top_k=int(top_k_plans),
                        library=library,
                        requirements=requirements,
                        fabric_width=float(fabric_width),
                        max_marker_length=float(max_marker_length),
                        max_distinct_sizes=int(max_distinct_sizes),
                        target_marker_length=float(target_marker_length),
                        max_markers=int(max_markers),
                        random_iterations=int(random_iterations),
                        allow_overproduction=bool(allow_overproduction),
                    )
            except (PlanGenerationError, ValueError) as error:
                st.error(str(error))
            except Exception as error:
                st.exception(error)

    alternatives = st.session_state.get("layer_alternatives", [])
    if alternatives:
        st.subheader("Planes recomendados")
        plan_rows = [
            {
                "Plan": alternative.plan_id,
                "Capas": alternative.layers,
                "Marcadores": alternative.marker_count,
                "Largo acumulado": alternative.total_length,
                "Eficiencia rectangular %": alternative.average_efficiency * 100,
                "Faltante": alternative.shortage,
                "Sobreproducción": alternative.overproduction,
                "Puntuación": alternative.score,
            }
            for alternative in alternatives
        ]
        st.dataframe(
            pd.DataFrame(plan_rows),
            hide_index=True,
            use_container_width=True,
            column_config={
                "Largo acumulado": st.column_config.NumberColumn(format="%.2f"),
                "Eficiencia rectangular %": st.column_config.NumberColumn(format="%.2f%%"),
                "Puntuación": st.column_config.NumberColumn(format="%.2f"),
            },
        )

        selected_plan_id = st.selectbox(
            "Plan para revisar",
            [alternative.plan_id for alternative in alternatives],
            key="selected_plan_id",
        )
        selected_alternative = next(
            alternative
            for alternative in alternatives
            if alternative.plan_id == selected_plan_id
        )
        plan = selected_alternative.plan

        st.subheader(
            f"{selected_alternative.plan_id} · {selected_alternative.layers} capas"
        )
        metric_1, metric_2, metric_3, metric_4, metric_5 = st.columns(5)
        metric_1.metric("Capas", selected_alternative.layers)
        metric_2.metric("Marcadores", len(plan.markers))
        metric_3.metric("Largo acumulado", f"{plan.total_length:.2f}")
        metric_4.metric("Eficiencia", f"{plan.average_efficiency:.2%}")
        metric_5.metric("Sobreproducción", selected_alternative.overproduction)

        st.subheader("Marcadores del plan")
        st.dataframe(
            pd.DataFrame(marker_summary(plan)),
            hide_index=True,
            use_container_width=True,
            column_config={
                "Largo estimado": st.column_config.NumberColumn(format="%.2f"),
                "Eficiencia %": st.column_config.NumberColumn(format="%.2f%%"),
            },
        )

        st.subheader("Auditoría del plan completo")
        st.dataframe(pd.DataFrame(plan.audit), hide_index=True, use_container_width=True)

        selected_marker_id = st.selectbox(
            "Marcador para inspeccionar",
            [marker.marker_id for marker in plan.markers],
            key="selected_marker_id",
        )
        selected_marker = next(
            marker
            for marker in plan.markers
            if marker.marker_id == selected_marker_id
        )

        st.markdown(
            f"**Combinación:** {format_repetitions(selected_marker.repetitions)}  \n"
            f"**Capas:** {selected_marker.layers}  \n"
            f"**Tallas diferentes:** {selected_marker.distinct_sizes}  \n"
            f"**Largo 2D:** {selected_marker.estimated_length:.2f} de "
            f"{max_marker_length:.2f} máximo  \n"
            f"**Método:** `{selected_marker.strategy}`"
        )

        st.plotly_chart(
            packing_figure(
                selected_marker.packing,
                title=(
                    f"{selected_marker.marker_id} · "
                    f"{selected_marker.layers} capas"
                ),
            ),
            use_container_width=True,
        )

        st.subheader("Coordenadas de colocación")
        st.dataframe(
            placement_table(selected_marker),
            hide_index=True,
            use_container_width=True,
            column_config={
                "X": st.column_config.NumberColumn(format="%.2f"),
                "Y": st.column_config.NumberColumn(format="%.2f"),
                "Ancho": st.column_config.NumberColumn(format="%.2f"),
                "Largo": st.column_config.NumberColumn(format="%.2f"),
                "X final": st.column_config.NumberColumn(format="%.2f"),
                "Y final": st.column_config.NumberColumn(format="%.2f"),
            },
        )

        st.subheader("Auditoría de piezas del marcador")
        piece_audit = marker_piece_audit(library, selected_marker)
        st.dataframe(piece_audit, hide_index=True, use_container_width=True)

        if piece_audit.empty or (piece_audit["Estado"] == "Completo").all():
            st.success(
                "Todas las piezas esperadas están completas dentro del marcador."
            )
        else:
            st.error(
                "El marcador contiene diferencias de integridad y no debe generarse."
            )


with tab_method:
    st.markdown(
        """
### Lógica activa

1. El CUT se interpreta con **Y como ancho transversal** y **X como largo longitudinal**.
2. Cada pieza se representa mediante su rectángulo envolvente `Ancho × Largo`.
3. Cada cantidad de capas dentro del rango se evalúa como una alternativa productiva.
4. Para cada marcador se prueban diversas heurísticas **MaxRects** y distintos órdenes de piezas.
5. Las piezas reciben coordenadas `X/Y`; los huecos rectangulares pueden reutilizarse.
6. Todas las piezas de una repetición permanecen dentro del mismo marcador.
7. El sistema conserva una lista corta de planes según largo, eficiencia, cantidad de marcadores y sobreproducción.

### Alcance

Este motor realiza **packing rectangular 2D**. Todavía no utiliza concavidades,
curvas ni colisiones entre los contornos reales de las piezas, y no sustituye el
nesting poligonal de AccuNest. La rotación automática permanece desactivada hasta
disponer de información fiable sobre sentido de hilo y orientaciones permitidas.
        """
    )
