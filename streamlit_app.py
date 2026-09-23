import pandas as pd
import streamlit as st

from core.cut_parser import LibraryNormalizationError, normalize_library, parse_cut
from core.cut_library import consolidate_cut_libraries
from core.plan_optimizer import PlanGenerationError, generate_marker_plan, marker_summary
from core.validation import validate
from exports import library_excel
from visualization import candidate_figure, cut_figure

st.set_page_config(page_title="Predictor AccuMark / AccuNest", page_icon="📐", layout="wide")
st.title("Predictor de combinaciones AccuMark / AccuNest")
st.caption("Analiza CUT/TXT y propone una lista operativa de marcadores completos.")

@st.cache_data
def load_examples():
    return pd.read_csv("data/piezas_ejemplo.csv"), pd.read_csv("data/requerimientos_ejemplo.csv")

if "library" not in st.session_state or "requirements" not in st.session_state:
    lib0, req0 = load_examples()
    st.session_state.setdefault("library", lib0)
    st.session_state.setdefault("requirements", req0)

def format_repetitions(repetitions):
    return ", ".join(f"{key.replace('|', ' ')} x {qty}" for key, qty in sorted(repetitions.items()))

def marker_piece_audit(library, marker):
    expected, actual = {}, {}
    for _, row in library.iterrows():
        key = f"{row['Modelo']}|{row['Talla']}"
        reps = int(marker.repetitions.get(key, 0))
        if reps:
            pkey = (str(row["Modelo"]), str(row["Talla"]), str(row["Pieza"]))
            expected[pkey] = reps * int(row["Cantidad"])
    for block in marker.blocks:
        for piece in block.pieces:
            pkey = (str(piece.model), str(piece.size), str(piece.piece))
            actual[pkey] = actual.get(pkey, 0) + 1
    return pd.DataFrame([
        {"Modelo": key[0], "Talla": key[1], "Pieza": key[2], "Esperado": expected.get(key, 0),
         "Encontrado": actual.get(key, 0), "Estado": "Completo" if expected.get(key, 0) == actual.get(key, 0) else "Revisar"}
        for key in sorted(set(expected) | set(actual))
    ])

tab_cut, tab_plan, tab_method = st.tabs(["1. Analizador CUT/TXT", "2. Plan de marcadores", "3. Metodología"])

with tab_cut:
    uploads = st.file_uploader("Cargue uno o varios archivos CUT/TXT", type=["cut", "txt"], accept_multiple_files=True)
    if uploads:
        signature = tuple((f.name, len(f.getvalue())) for f in uploads)
        if st.session_state.get("upload_signature") != signature:
            st.session_state.parsed_cut = [parse_cut(f.getvalue(), f.name) for f in uploads]
            st.session_state.upload_signature = signature
    parsed_files = st.session_state.get("parsed_cut", [])
    if parsed_files:
        diagnostics = pd.DataFrame([p["diagnostic"] for p in parsed_files])
        st.subheader("Diagnóstico")
        st.dataframe(diagnostics, hide_index=True, use_container_width=True)
        detected, conflicts = consolidate_cut_libraries(parsed_files)
        st.info("Ajuste RepeticionesTalla cuando el CUT contenga más de una repetición. La división debe ser exacta.")
        edited = st.data_editor(
            detected, num_rows="dynamic", use_container_width=True, key="detected_library_editor",
            disabled=["Modelo", "Talla", "Pieza", "InstanciasCUT", "Origenes", "IDRepresentante", "DimensionStatus"],
            column_config={
                "ConflictoCritico": st.column_config.CheckboxColumn("Conflicto crítico"),
                "RepeticionesTalla": st.column_config.NumberColumn("Repeticiones talla", min_value=1, step=1, format="%d"),
                "Ancho": st.column_config.NumberColumn("Ancho", min_value=0.0001, format="%.4f"),
                "Largo": st.column_config.NumberColumn("Largo", min_value=0.0001, format="%.4f"),
            },
        )
        if not conflicts.empty:
            st.error("Existen conflictos críticos entre los CUT cargados.")
            st.dataframe(conflicts, hide_index=True, use_container_width=True)
        normalized, normalization_errors = None, pd.DataFrame()
        try:
            normalized = normalize_library(edited)
        except LibraryNormalizationError as error:
            normalization_errors = error.to_frame()
            st.error("La biblioteca todavía no es válida. Corrija los errores indicados.")
            st.dataframe(normalization_errors, hide_index=True, use_container_width=True)
        st.subheader("Biblioteca normalizada")
        if normalized is not None:
            st.dataframe(normalized, hide_index=True, use_container_width=True)
        else:
            st.caption("No disponible hasta resolver los errores críticos.")
        unresolved = bool(edited.get("ConflictoCritico", pd.Series(False, index=edited.index)).fillna(False).astype(bool).any())
        valid = normalized is not None and conflicts.empty and normalization_errors.empty and not unresolved
        c1, c2 = st.columns(2)
        if c1.button("Usar biblioteca detectada", type="primary", use_container_width=True, disabled=not valid):
            st.session_state.library = normalized.drop(columns=["Unidad", "Confianza"], errors="ignore")
            st.session_state.pop("marker_plan", None)
            st.success("Biblioteca enviada al planificador.")
        if valid:
            c2.download_button("Descargar biblioteca y diagnóstico", library_excel(normalized, diagnostics), "biblioteca_cut.xlsx", use_container_width=True)
        else:
            c2.button("Descargar biblioteca y diagnóstico", disabled=True, use_container_width=True)
        selected_name = st.selectbox("Archivo para visualizar", [p["diagnostic"]["Archivo"] for p in parsed_files])
        selected = next(p for p in parsed_files if p["diagnostic"]["Archivo"] == selected_name)
        st.plotly_chart(cut_figure(selected), use_container_width=True)
    else:
        st.info("Cargue un CUT/TXT para construir la biblioteca.")

with tab_plan:
    with st.sidebar:
        st.header("Configuración del plan")
        fabric_width = st.number_input("Ancho de tela", min_value=0.01, value=80.0, step=0.5)
        layers = st.number_input("Capas por marcador", min_value=1, value=50, step=1)
        st.subheader("Límites obligatorios")
        max_marker_length = st.number_input("Largo máximo por marcador", min_value=1.0, value=500.0, step=10.0)
        # FIX: no usa max_value dinámico, evitando pantalla en blanco por estado anterior.
        target_input = st.number_input("Largo objetivo por marcador", min_value=1.0, value=450.0, step=10.0)
        target_marker_length = min(float(target_input), float(max_marker_length))
        if target_input > max_marker_length:
            st.warning(f"El objetivo supera el máximo. Para este cálculo se utilizará {target_marker_length:.2f}.")
        max_distinct_sizes = st.number_input("Máximo de tallas diferentes", min_value=1, value=3, step=1)
        max_markers = st.number_input("Máximo de marcadores del plan", min_value=1, value=20, step=1)
        st.subheader("Búsqueda")
        random_iterations = st.slider("Iteraciones por propuesta", 0, 40, 8)
        allow_overproduction = st.checkbox("Completar divisiones no enteras con sobreproducción", value=True)

    st.subheader("Datos de entrada")
    left, right = st.columns(2)
    with left:
        library = st.data_editor(st.session_state.library, num_rows="dynamic", use_container_width=True, key="plan_library_editor")
    with right:
        requirements = st.data_editor(st.session_state.requirements, num_rows="dynamic", use_container_width=True, key="plan_requirements_editor")
    st.session_state.library, st.session_state.requirements = library, requirements

    if st.button("Generar lista de marcadores propuestos", type="primary", use_container_width=True):
        errors = validate(library, requirements)
        if errors:
            for error in errors:
                st.error(error)
        else:
            try:
                with st.spinner("Generando marcadores completos..."):
                    st.session_state.marker_plan = generate_marker_plan(
                        library=library, requirements=requirements, fabric_width=float(fabric_width), layers=int(layers),
                        max_marker_length=float(max_marker_length), max_distinct_sizes=int(max_distinct_sizes),
                        target_marker_length=float(target_marker_length), max_markers=int(max_markers),
                        random_iterations=int(random_iterations), allow_overproduction=bool(allow_overproduction),
                    )
            except PlanGenerationError as error:
                st.error(str(error))
            except Exception as error:
                st.exception(error)

    plan = st.session_state.get("marker_plan")
    if plan:
        st.subheader("Lista de marcadores propuestos")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Marcadores", len(plan.markers))
        c2.metric("Largo acumulado", f"{plan.total_length:.2f}")
        c3.metric("Eficiencia promedio", f"{plan.average_efficiency:.2%}")
        c4.metric("Integridad", "Completa" if plan.integrity_ok and plan.coverage_ok else "Revisar")
        st.dataframe(pd.DataFrame(marker_summary(plan)), hide_index=True, use_container_width=True)
        st.subheader("Auditoría del plan completo")
        st.dataframe(pd.DataFrame(plan.audit), hide_index=True, use_container_width=True)
        marker_id = st.selectbox("Marcador para inspeccionar", [m.marker_id for m in plan.markers])
        marker = next(m for m in plan.markers if m.marker_id == marker_id)
        st.markdown(
            f"**Combinación:** {format_repetitions(marker.repetitions)}  \n"
            f"**Capas:** {marker.layers}  \n**Tallas diferentes:** {marker.distinct_sizes}  \n"
            f"**Largo:** {marker.estimated_length:.2f} de {max_marker_length:.2f} máximo"
        )
        st.plotly_chart(candidate_figure(marker), use_container_width=True)
        st.subheader("Auditoría de piezas del marcador")
        piece_audit = marker_piece_audit(library, marker)
        st.dataframe(piece_audit, hide_index=True, use_container_width=True)
        if piece_audit.empty or (piece_audit["Estado"] == "Completo").all():
            st.success("Todas las piezas están completas dentro del marcador.")
        else:
            st.error("El marcador contiene diferencias de integridad.")

with tab_method:
    st.markdown("""
### Reglas principales
- Cada `MK-###` es un marcador independiente.
- Los bloques son secciones del mismo marcador.
- Una repetición nunca se divide entre marcadores.
- El largo máximo y el máximo de tallas son restricciones duras.
- La eficiencia es rectangular y predictiva; no sustituye AccuNest.
- La biblioteca CUT conserva pares reales Ancho-Largo y bloquea conflictos sin resolver.
""")
