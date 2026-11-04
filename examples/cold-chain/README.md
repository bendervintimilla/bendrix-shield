# Cadena de frío (IoT) — Refrigeración

Dispositivo «Refrigeración» con token Shield propio y alcance mínimo
(`coldchain:read`, `coldchain:setpoint:camara`,
`coldchain:setpoint:congelador`).

Un atacante con el token robado intenta subir la cámara a 15 °C y el
congelador a 5 °C a las 03:00 desde otro país. wAIrrior detecta las tres
señales (fuera de rango, fuera de horario, origen inesperado), bloquea
sin mover el equipo, el dueño confirma por voz («sí, rota
refrigeración») y solo ese token pasa a 401: Refrigeración con su
token nuevo, Bodega y Compras siguen en 200.

```bash
uv run python examples/cold-chain/run.py   # escenario replay, sin red
uv run python evals/run_cold_chain.py     # eval + grabación + report.md
make demo                                  # incluye este escenario
```

Grabación de replay para la demo en línea:
`evals/recorded/cold-chain-replay.json` (sin tokens en claro).
