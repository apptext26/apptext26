import pandas as pd
import streamlit as st

from core import (
    parse_cut,
    normalize_library,
    validate,
    generate_marker_plan,
    marker_summary,
    PlanGenerationError,
)
from visualization import cut_figure, candidate_figure
from exports import library_excel


st.set_page_config(
    page_title="Predictor AccuMark / AccuNest",
    page_icon="📐",
    layout="wide",
)

st.title("Predictor de combinaciones AccuMark / AccuNest")
st.caption(
    "Analiza CUT/TXT y propone una lista operativa de marcadores. "
    "Cada marcador conserva completas las piezas de cada repetición."
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
        key = (str(row["Modelo"]), str(row["Talla"]), str(row["Pieza"]))
        expected[key] = repetitions * int(row["Cantidad"])

    actual = {}
    for block in marker.blocks:
        for piece in block.pieces:
            key = (str(piece.model), str(piece.size), str(piece.piece))
            actual[key] = actual.get(key, 0) + 1

    rows = []
    for key in sorted(set(expected) | set(actual)):
        wanted = expected.get(key, 0)
        found = actual.get(key, 0)
        rows.append(
            {
                "Modelo": key[0],
                "Talla": key[1],
                "Pieza": key[2],
                "Esperado": wanted,
                "Encontrado": found,
                "Estado": "Completo" if wanted == found else "Revisar",
            }
        )
    return pd.DataFrame(rows)


tab_cut, tab_plan, tab_method = st.tabs(
    ["1. Analizador CUT/TXT", "2. Plan de marcadores", "3. Metodología"]
)


with tab_cut:
    uploads = st.file_uploader(
        "Cargue uno o varios archivos CUT/TXT",
        type=["cut", "txt"],
        accept_multiple_files=True,
    )

    if uploads:
        st.session_state.parsed_cut = [
            parse_cut(upload.getvalue(), upload.name) for upload in uploads
        ]

    parsed_files = st.session_state.get("parsed_cut", [])
    if parsed_files:
        diagnostics = pd.DataFrame(
            [parsed["diagnostic"] for parsed in parsed_files]
        )
        st.subheader("Diagnóstico")
        st.dataframe(diagnostics, hide_index=True, use_container_width=True)

        detected = pd.concat(
            [parsed["library"] for parsed in parsed_files],
            ignore_index=True,
        )
        detected = detected.groupby(
            ["Modelo", "Talla", "Pieza"], as_index=False
        ).agg(
            InstanciasCUT=("InstanciasCUT", "max"),
            RepeticionesTalla=("RepeticionesTalla", "max"),
            Cantidad=("Cantidad", "max"),
            Ancho=("Ancho", "max"),
            Largo=("Largo", "max"),
            Unidad=("Unidad", "first"),
            Confianza=("Confianza", "min"),
        )

        st.info(
            "InstanciasCUT es la cantidad encontrada físicamente en el marcador. "
            "Ajuste RepeticionesTalla si el archivo contiene más de una repetición."
        )
        detected_edited = st.data_editor(
            detected,
            num_rows="dynamic",
            use_container_width=True,
            key="detected_library_editor",
        )
        normalized = normalize_library(detected_edited)

        st.subheader("Biblioteca normalizada")
        st.dataframe(normalized, hide_index=True, use_container_width=True)

        left, right = st.columns(2)
        if left.button(
            "Usar biblioteca detectada",
            type="primary",
            use_container_width=True,
        ):
            st.session_state.library = normalized.drop(
                columns=["Unidad", "Confianza"], errors="ignore"
            )
            st.success("La biblioteca fue enviada al generador de planes.")

        right.download_button(
            "Descargar biblioteca y diagnóstico",
            library_excel(normalized, diagnostics),
            "biblioteca_cut.xlsx",
            use_container_width=True,
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
        st.info("Cargue un CUT/TXT para construir automáticamente la biblioteca.")


with tab_plan:
    with st.sidebar:
        st.header("Configuración del plan")
        fabric_width = st.number_input(
            "Ancho de tela",
            min_value=0.01,
            value=80.0,
            step=0.5,
        )
        layers = st.number_input(
            "Capas por marcador",
            min_value=1,
            value=50,
            step=1,
        )

        st.subheader("Límites obligatorios")
        max_marker_length = st.number_input(
            "Largo máximo por marcador",
            min_value=1.0,
            value=500.0,
            step=10.0,
            help="Ningún marcador propuesto podrá superar este largo.",
        )
        target_marker_length = st.number_input(
            "Largo objetivo por marcador",
            min_value=1.0,
            value=450.0,
            step=10.0,
            help="El motor intenta cerrar el marcador al alcanzar este objetivo.",
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

        st.subheader("Búsqueda")
        random_iterations = st.slider(
            "Iteraciones por propuesta",
            min_value=0,
            max_value=40,
            value=8,
        )
        allow_overproduction = st.checkbox(
            "Completar divisiones no enteras con sobreproducción",
            value=True,
        )

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

    if target_marker_length > max_marker_length:
        st.warning(
            "El largo objetivo es mayor que el largo máximo. "
            "El motor utilizará el largo máximo como objetivo."
        )

    if st.button(
        "Generar lista de marcadores propuestos",
        type="primary",
        use_container_width=True,
    ):
        input_errors = validate(library, requirements)
        if input_errors:
            for error in input_errors:
                st.error(error)
        else:
            try:
                with st.spinner(
                    "Dividiendo la demanda y evaluando marcadores completos..."
                ):
                    st.session_state.marker_plan = generate_marker_plan(
                        library=library,
                        requirements=requirements,
                        fabric_width=float(fabric_width),
                        layers=int(layers),
                        max_marker_length=float(max_marker_length),
                        max_distinct_sizes=int(max_distinct_sizes),
                        target_marker_length=float(target_marker_length),
                        max_markers=int(max_markers),
                        random_iterations=int(random_iterations),
                        allow_overproduction=bool(allow_overproduction),
                    )
            except PlanGenerationError as error:
                st.error(str(error))
            except Exception as error:
                st.exception(error)

    plan = st.session_state.get("marker_plan")
    if plan:
        st.subheader("Lista de marcadores propuestos")

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Marcadores", len(plan.markers))
        col2.metric("Largo acumulado", f"{plan.total_length:.2f}")
        col3.metric("Eficiencia promedio", f"{plan.average_efficiency:.2%}")
        col4.metric(
            "Integridad",
            "Completa" if plan.integrity_ok and plan.coverage_ok else "Revisar",
        )

        summary = pd.DataFrame(marker_summary(plan))
        st.dataframe(
            summary,
            hide_index=True,
            use_container_width=True,
            column_config={
                "Largo estimado": st.column_config.NumberColumn(format="%.2f"),
                "Eficiencia %": st.column_config.NumberColumn(format="%.2f%%"),
            },
        )

        st.subheader("Auditoría del plan completo")
        audit = pd.DataFrame(plan.audit)
        st.dataframe(audit, hide_index=True, use_container_width=True)

        selected_marker_id = st.selectbox(
            "Marcador para inspeccionar",
            [marker.marker_id for marker in plan.markers],
        )
        selected_marker = next(
            marker
            for marker in plan.markers
            if marker.marker_id == selected_marker_id
        )

        st.markdown(
            f"**Combinación:** {format_repetitions(selected_marker.repetitions)}  "
            f"\n**Capas:** {selected_marker.layers}  "
            f"\n**Tallas diferentes:** {selected_marker.distinct_sizes}  "
            f"\n**Largo:** {selected_marker.estimated_length:.2f} de "
            f"{max_marker_length:.2f} máximo"
        )

        st.plotly_chart(
            candidate_figure(selected_marker),
            use_container_width=True,
        )

        st.subheader("Auditoría de piezas del marcador")
        piece_audit = marker_piece_audit(library, selected_marker)
        st.dataframe(piece_audit, hide_index=True, use_container_width=True)

        invalid_rows = piece_audit[piece_audit["Estado"] != "Completo"]
        if invalid_rows.empty:
            st.success(
                "Todas las piezas de cada modelo y talla están completas "
                "dentro de este marcador."
            )
        else:
            st.error("El marcador contiene diferencias de integridad y no debe generarse.")


with tab_method:
    st.markdown(
        """
### Interpretación del resultado

- Un **plan** contiene una lista pequeña de marcadores propuestos.
- Cada `MK-###` es un marcador independiente que puede enviarse a generar.
- Los bloques `B1`, `B2`, etc. son secciones consecutivas del mismo marcador.
- Una repetición nunca se divide entre marcadores: BK, FT, SL y cualquier otra
  pieza requerida permanecen juntas dentro del mismo marcador.
- El largo máximo y el máximo de tallas diferentes son restricciones duras.
- Si una propuesta supera cualquiera de los límites, no se incorpora al plan.
- La eficiencia continúa siendo rectangular y predictiva; no sustituye el
  anidado geométrico real de AccuNest.

### Objetivo del generador

El motor intenta producir pocos marcadores, cercanos al largo objetivo, con
buena eficiencia y cumplimiento completo de la demanda. El resultado es una
propuesta operativa que debe validarse finalmente en AccuNest.
        """
    )
