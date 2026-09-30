"""Búsqueda con relajación progresiva de límites "preferibles".

Motivación
----------
Antes, si la demanda no cabía dentro de los parámetros EXACTOS que el
usuario configuró (capas, marcadores, largo de marcador...), la app fallaba
con un error genérico ("Ninguna cantidad de capas produjo un plan viable.")
y no intentaba nada más. Este módulo envuelve la búsqueda normal
(`evaluate_layer_range` + `generate_mixed_alternatives`) para, cuando eso
ocurre, probar en orden versiones cada vez más permisivas de los límites
que son preferencias de planificación -- nunca del ancho de tela, que es
un límite físico real (el rollo de tela mide lo que mide) y jamás se toca
en este módulo.

Orden de relajación
--------------------
Cada paso conserva los ajustes de los pasos anteriores (son acumulativos)
y se detiene en el primer paso que logra cubrir el 100% de la demanda:

    0. Exactamente lo que el usuario configuró.
    1. Muestreo de capas más denso, dentro del MISMO rango solicitado
       (no cambia ningún límite; solo prueba más valores de capas).
    2. Más marcadores permitidos (x1.5, x2, x3, con tope de seguridad).
    3. Más capas máximas permitidas (x2, x4, con tope de seguridad).
    4. Marcador más largo (x1.15, x1.4, con tope de seguridad) -- el
       último recurso, porque de los cuatro es el que más se acerca a un
       límite físico real (mesa/tendido).
    5. Más tallas distintas permitidas por marcador.

Si ningún paso logra cobertura completa, se conserva el mejor intento
visto en TODA la búsqueda (menor faltante y, a igualdad, menor consumo) y
se marca explícitamente como incompleto. Nunca se disfraza un plan parcial
como una solución completa.

La caché de empaques (`packing_cache`) se comparte entre todos los pasos:
los pasos 1 a 3 no cambian `fabric_width` ni `max_marker_length`, así que
reutilizan geometría ya calculada y no repiten el trabajo caro del
packing 2D desde cero.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .layer_optimizer import LayerPlanAlternative, evaluate_layer_range
from .mixed_layer_optimizer import generate_mixed_alternatives
from .plan_optimizer import PlanGenerationError, generate_marker_plan


# Topes de seguridad: ninguna relajación automática puede superarlos, sin
# importar cuántos pasos se acumulen. Evitan corridas absurdamente largas
# o resultados sin sentido industrial (p. ej. 5000 capas).
MAX_MARKERS_CEILING = 200
MAX_LAYERS_CEILING = 4000
MAX_LENGTH_MULTIPLIER_CEILING = 1.4
MAX_DISTINCT_SIZES_CEILING = 12


@dataclass
class RelaxationStep:
    etiqueta: str
    parametro: str
    valor_original: Any
    valor_usado: Any
    resultado: str  # "cobertura_completa" | "parcial" | "sin_plan"
    faltante_minimo: int = 0


@dataclass
class PreferenceSolution:
    complete: bool
    alternatives: list  # list[LayerPlanAlternative], cobertura completa, ya ordenadas
    best_partial: "LayerPlanAlternative | None"
    relaxed: bool
    steps: list[RelaxationStep]
    trace: list[dict]
    effective_settings: dict
    requested_settings: dict


def _attempt(
    *, library, requirements, fabric_width, max_marker_length,
    target_marker_length, max_distinct_sizes, max_markers,
    layers_min, layers_max, layer_step, max_layer_trials, top_k,
    random_iterations, allow_overproduction, packing_budget,
    mixed_enabled, residual_trials, packing_cache, trace_sink,
) -> list:
    """Una pasada completa (uniforme + mixta si aplica). Devuelve TODAS las
    alternativas, incluidas las que no cubren el 100% de la demanda, para
    poder comparar el mejor intento aunque nada logre cobertura completa."""
    uniform_trace: list[dict] = []
    uniform = evaluate_layer_range(
        plan_factory=generate_marker_plan,
        layers_min=int(layers_min), layers_max=int(layers_max),
        layer_step=int(layer_step), max_layer_trials=int(max_layer_trials),
        diagnostics=uniform_trace, top_k=int(top_k),
        library=library, requirements=requirements,
        fabric_width=float(fabric_width), max_marker_length=float(max_marker_length),
        max_distinct_sizes=int(max_distinct_sizes),
        target_marker_length=float(min(target_marker_length, max_marker_length)),
        max_markers=int(max_markers), random_iterations=int(random_iterations),
        allow_overproduction=bool(allow_overproduction),
        packing_budget=int(packing_budget), packing_cache=packing_cache,
    )
    trace_sink.extend(uniform_trace)
    mixed: list = []
    if mixed_enabled:
        mixed, extra_trace = generate_mixed_alternatives(
            uniform_alternatives=uniform, plan_factory=generate_marker_plan,
            library=library, requirements=requirements,
            layers_min=int(layers_min), layers_max=int(layers_max),
            layer_step=int(layer_step), max_markers=int(max_markers),
            allow_overproduction=bool(allow_overproduction),
            max_residual_trials=int(residual_trials),
            fabric_width=float(fabric_width), max_marker_length=float(max_marker_length),
            max_distinct_sizes=int(max_distinct_sizes),
            target_marker_length=float(min(target_marker_length, max_marker_length)),
            random_iterations=int(random_iterations),
            packing_budget=int(packing_budget), packing_cache=packing_cache,
        )
        trace_sink.extend(extra_trace)
    return list(uniform) + list(mixed)


def solve_with_preferences(
    *, library, requirements, fabric_width, max_marker_length, target_marker_length,
    max_distinct_sizes, max_markers, layers_min, layers_max, layer_step,
    max_layer_trials, top_k, random_iterations, allow_overproduction,
    packing_budget, mixed_enabled, residual_trials, allow_relaxation=True,
) -> PreferenceSolution:
    """Ejecuta la búsqueda y, si hace falta y `allow_relaxation` está
    activo, relaja progresivamente los límites preferibles hasta lograr
    cobertura completa o agotar los pasos definidos."""
    packing_cache: dict = {}
    trace: list[dict] = []
    steps: list[RelaxationStep] = []
    pool: list = []

    requested_settings = dict(
        fabric_width=fabric_width, max_marker_length=max_marker_length,
        target_marker_length=target_marker_length, max_distinct_sizes=max_distinct_sizes,
        max_markers=max_markers, layers_min=layers_min, layers_max=layers_max,
        layer_step=layer_step, max_layer_trials=max_layer_trials,
    )
    cfg = dict(requested_settings)

    def run(label: str, param_name: str | None = None, original=None, used=None):
        try:
            alts = _attempt(
                library=library, requirements=requirements,
                fabric_width=cfg["fabric_width"], max_marker_length=cfg["max_marker_length"],
                target_marker_length=cfg["target_marker_length"],
                max_distinct_sizes=cfg["max_distinct_sizes"], max_markers=cfg["max_markers"],
                layers_min=cfg["layers_min"], layers_max=cfg["layers_max"],
                layer_step=cfg["layer_step"], max_layer_trials=cfg["max_layer_trials"],
                top_k=top_k, random_iterations=random_iterations,
                allow_overproduction=allow_overproduction, packing_budget=packing_budget,
                mixed_enabled=mixed_enabled, residual_trials=residual_trials,
                packing_cache=packing_cache, trace_sink=trace,
            )
        except (PlanGenerationError, ValueError) as error:
            trace.append({
                "Fase": "relajación", "Paso": label, "Estado": "error",
                "Detalle": str(error)[:240],
            })
            alts = []

        pool.extend(alts)
        complete = [a for a in alts if not a.shortage and a.plan.integrity_ok]
        if param_name is not None:
            best_shortage = min((a.shortage for a in alts), default=0)
            steps.append(RelaxationStep(
                etiqueta=label, parametro=param_name,
                valor_original=original, valor_usado=used,
                resultado=(
                    "cobertura_completa" if complete
                    else ("parcial" if alts else "sin_plan")
                ),
                faltante_minimo=int(best_shortage),
            ))
        return complete

    def finish(complete: list, relaxed: bool) -> PreferenceSolution:
        if complete:
            ranked = sorted(
                complete,
                key=lambda a: (a.shortage, a.consumption, a.overproduction, a.marker_count),
            )
            return PreferenceSolution(
                complete=True, alternatives=ranked, best_partial=None,
                relaxed=relaxed, steps=steps, trace=trace,
                effective_settings=dict(cfg), requested_settings=requested_settings,
            )
        best_partial = None
        if pool:
            best_partial = min(
                pool, key=lambda a: (a.shortage, a.overproduction, a.consumption)
            )
        return PreferenceSolution(
            complete=False, alternatives=[], best_partial=best_partial,
            relaxed=relaxed, steps=steps, trace=trace,
            effective_settings=dict(cfg), requested_settings=requested_settings,
        )

    # Paso 0: exactamente lo pedido.
    complete = run("Parámetros exactos")
    if complete or not allow_relaxation:
        return finish(complete, relaxed=False)

    # Paso 1: muestreo de capas más denso, mismo rango solicitado.
    total_layer_values = ((int(layers_max) - int(layers_min)) // int(layer_step)) + 1
    denser = min(total_layer_values, max(int(max_layer_trials) * 3, 24), 60)
    if denser > cfg["max_layer_trials"]:
        original = cfg["max_layer_trials"]
        cfg["max_layer_trials"] = denser
        complete = run("Muestreo de capas más denso", "max_layer_trials", original, denser)
        if complete:
            return finish(complete, relaxed=True)

    # Paso 2: más marcadores permitidos.
    for factor in (1.5, 2.0, 3.0):
        candidate = min(MAX_MARKERS_CEILING, max(cfg["max_markers"] + 1, round(max_markers * factor)))
        if candidate <= cfg["max_markers"]:
            continue
        original = cfg["max_markers"]
        cfg["max_markers"] = candidate
        complete = run(f"Más marcadores permitidos (x{factor:g})", "max_markers", original, candidate)
        if complete:
            return finish(complete, relaxed=True)

    # Paso 3: más capas máximas permitidas (menos repeticiones por talla).
    for factor in (2.0, 4.0):
        candidate = min(MAX_LAYERS_CEILING, max(cfg["layers_max"] + 1, round(layers_max * factor)))
        if candidate <= cfg["layers_max"]:
            continue
        original = cfg["layers_max"]
        cfg["layers_max"] = candidate
        complete = run(f"Más capas máximas permitidas (x{factor:g})", "layers_max", original, candidate)
        if complete:
            return finish(complete, relaxed=True)

    # Paso 4: marcador más largo (último recurso: el más cercano a un
    # límite físico real de mesa/tendido).
    for factor in (1.15, MAX_LENGTH_MULTIPLIER_CEILING):
        candidate = round(max_marker_length * factor, 2)
        if candidate <= cfg["max_marker_length"]:
            continue
        original = cfg["max_marker_length"]
        cfg["max_marker_length"] = candidate
        cfg["target_marker_length"] = min(cfg["target_marker_length"], candidate)
        complete = run(f"Marcador más largo (x{factor:g})", "max_marker_length", original, candidate)
        if complete:
            return finish(complete, relaxed=True)

    # Paso 5: más tallas distintas por marcador.
    candidate = min(MAX_DISTINCT_SIZES_CEILING, cfg["max_distinct_sizes"] + 2)
    if candidate > cfg["max_distinct_sizes"]:
        original = cfg["max_distinct_sizes"]
        cfg["max_distinct_sizes"] = candidate
        complete = run("Más tallas distintas por marcador", "max_distinct_sizes", original, candidate)
        if complete:
            return finish(complete, relaxed=True)

    return finish([], relaxed=True)
