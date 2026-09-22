# Predictor AccuMark / AccuNest - MVP

Prototipo para evaluar combinaciones productivas y distribuciones rectangulares antes de enviar candidatos a AccuNest.

## Funcionalidad incluida

- Biblioteca de piezas editable o importada desde Excel/CSV.
- Requerimientos editables o importados desde Excel/CSV.
- Evaluación de rangos de capas.
- Repeticiones enteras por talla mediante alternativas de piso y techo.
- Expansión a piezas individuales.
- Heurísticas de bloques: ancho, largo y área descendentes; mejor ajuste; aleatoria repetida.
- Cálculo de producción, faltantes, sobreproducción, largo y eficiencia rectangular.
- Ranking configurable.
- Visualización proporcional de bloques.
- Exportación a Excel con varias hojas.
- Pruebas automáticas del caso L obligatorio.

## Instalación

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/macOS
source .venv/bin/activate
pip install -r requirements.txt
```

## Ejecución

```bash
streamlit run streamlit_app.py
```

## Pruebas

```bash
pytest -q
```

## Caso de validación

La biblioteca de ejemplo incluye talla L con FT=1, BK=1, SL=2. Para 100 unidades, 50 capas y ancho 72, el motor genera 2 FT, 2 BK y 4 SL. La distribución de referencia puede producir largo 53 y eficiencia 71.38%, aunque el motor también busca alternativas mejores bajo la misma aproximación rectangular.

## Nota metodológica

Este predictor no reemplaza el anidado geométrico de AccuNest. Usa rectángulos envolventes para comparar candidatos de forma consistente.


## Publicación en Streamlit Community Cloud

1. Cree un repositorio nuevo en GitHub.
2. Suba el contenido de esta carpeta a la raíz del repositorio.
3. Entre a https://share.streamlit.io e inicie sesión con GitHub.
4. Seleccione **Create app**.
5. Seleccione el repositorio y la rama principal.
6. En **Main file path**, indique `streamlit_app.py`.
7. Pulse **Deploy**.

No se requieren secretos para esta versión. Los datos cargados por el usuario se procesan durante la sesión y no se guardan permanentemente.
