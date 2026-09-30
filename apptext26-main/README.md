# Predictor AccuMark / AccuNest V2

## Funciones
- Parser CUT/TXT híbrido validado con archivos CR y LF.
- Detección de marcador, modelo, tallas, piezas, lados y dimensiones.
- Biblioteca editable y exportable.
- Vista geométrica.
- Predictor rectangular.
- Agrupación de candidatos duplicados.

## Parámetros como preferencias, no obligaciones
Ancho de tela y largo/pieza individuales siguen siendo límites físicos
duros (no se pueden relajar: dependen de la tela y la mesa reales). Pero
`Máximo de marcadores`, `Capas máximas`, `Largo máximo por marcador` y
`Máximo de tallas por marcador` son preferencias de planificación: si la
demanda no cabe dentro de ellas, la app (`core/relaxation.py`) las relaja
progresivamente —en ese orden, con topes de seguridad— hasta cubrir el
100% de la demanda, y muestra exactamente qué tuvo que ajustar. Esto se
puede desactivar con el checkbox "Relajar automáticamente si no hay
solución exacta" en la pestaña de planes.

## Streamlit Community Cloud
Suba el contenido a la raíz de GitHub y use `streamlit_app.py` como Main file path.
