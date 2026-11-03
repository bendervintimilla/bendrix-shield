# crew/

Cliente cero de la demo: `orchestrator.py` (Spark 1.3 con tool calling)
más `compras/` (factura -> costo, Spark visión) y `bodega/` (conteo con
SAM 3.1 + voz). Todo vía SDK (`wrap`, `@shield.tool`, `untrusted`) y
gateway, con un token por agente (`build_crew`). Sin créditos corre en
replay con el router local determinista.

`refrigeracion/` (C2489-2): dispositivo de cadena de frío con token
propio y alcance mínimo (`coldchain:*`). Detecta setpoint fuera de
rango, fuera de horario y origen inesperado; el escenario replay
(`refrigeracion/scenario.py`) rota solo ese token tras la voz del
dueño y el atacante pasa a 401 mientras la cocina sigue en 200.
