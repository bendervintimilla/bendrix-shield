# wAIrrior Frontier: plan del 4-nov (meta: puesto 1, Indie track)

Hora de referencia: Nueva York (ET). Cierre del envío: **21:00 ET**.

## La idea en una línea
Los agentes de IA ya mueven cosas físicas (cámaras de frío, congeladores, hornos, bombas).
wAIrrior **simula la física antes de dejar actuar al agente**: un gemelo térmico predice qué
le pasa al producto si se ejecuta la acción y bloquea lo que rompe la envolvente segura, aunque
la orden venga bien escrita, en rango y con el token correcto. La decisión depende de la física,
no del texto, así que la inyección de instrucciones no alcanza.

Comparación que medimos (y publicamos con sus fallas):
1. Sin escudo.
2. Reglas estáticas (lo de hoy: rango, horario, origen).
3. Escudo predictivo físico (nuevo).
Ataques que las reglas estáticas NO ven: deriva lenta de setpoint (cada paso en rango),
apagado del compresor justo después de una carga caliente, deshielo largo con puerta abierta,
sensor falsificado que reporta 3 °C mientras el producto sube.

Modelos de Meta en la cadena: Muse Spark (agente controlador y explicación al dueño),
SAM 3.1 (lee la escena: cajas cargadas → masa térmica, puerta abierta), Muse Voice Transcribe
(aprobación del dueño), WhatsApp Cloud API (alerta). Todo con response ID y costo registrado.

## Contrato
`shield/physics/contract.py` es la única interfaz común. No cambies firmas: si hace falta,
escribe en tu ESTADO-Mx.md y espera al orquestador.

## Frentes (un dueño por archivo; no toques archivos de otro frente)
| ID | Rama | Archivos propios | Entrega |
|---|---|---|---|
| M1 | fx/m1-twin | shield/physics/thermal.py, shield/physics/gate.py, tests/test_physics_twin.py, tests/test_physics_gate.py | simulate() y verify_action() según el contrato, tests deterministas |
| M2 | fx/m2-bench | evals/physical/cases.json, evals/run_physical.py, tests/test_physical_bench.py | ≥30 casos (legítimos + ataques) y runner que compara 3 escudos; usa M1 cuando exista |
| M3 | fx/m3-sam | shield/physics/perception.py, tests/test_physics_perception.py, evals/recorded/physical-sam-*.json | SAM 3.1 → cajas/puerta → product_kg y door_open; corrida real registrada |
| M4 | fx/m4-controller | shield/physics/controller.py, tests/test_physics_controller.py, evals/recorded/physical-live-*.json | Muse Spark como agente controlador + explicación al dueño; corrida real registrada |
| M5 | fx/m5-scene | web/physical_scene.py, tests/test_physical_scene.py, ganchos mínimos en web/app.py y web/live_page.py | escena «Physical» en la demo pública (replay determinista con el gemelo y gráfico de trayectoria) |
| M6 | fx/m6-residual | shield/physics/residual.py, tests/test_physics_residual.py | detector de sensor falsificado por residuo físico |
| M7 | fx/m7-redteam | evals/physical/redteam.json, evals/run_physical_redteam.py, evals/physical/REDTEAM.md | intenta romper el escudo predictivo; publica lo que pasa |
| M8 | fx/m8-story | docs/FRONTIER.md, README (sección nueva arriba), scratch/frontier/envio-textos.json, scratch/frontier/guion-video.md | narrativa, textos del envío y guion del video (cifras como {{PLACEHOLDER}}) |
| M9 | (fuera del repo) | ~/Desktop/Hackathon-Meta/H19-video-frontier/ | pipeline de grabación/montaje del video nuevo, listo para grabar a las 18:15 |

## Reglas para todos
- Trabaja en tu worktree y tu rama. `git push -u origin <rama>` y PR en borrador contra `frontier`. No fusiones nada.
- Antes de cada push: `uv run pytest -q` y `uv run ruff check shield tests scripts web evals` en verde.
- Nada de cifras inventadas. Lo simulado se rotula «simulated». Parámetros físicos: supuestos rotulados o con fuente.
- Secretos nunca en el repo ni en la terminal: la llave de Meta se lee a una variable con
  `export META_MODEL_API_KEY=$(gcloud secrets versions access latest --secret=hackathon-meta-model-api-key --project=bendrix-hackathon)`
  y no se imprime. Tope de gasto por frente: USD 2.
- No despliegues nada. No toques main, ni Cloud Run, ni el formulario de Cerebral Valley.
- Progreso en `~/dev/wairrior-fx/ESTADO-<ID>.md` (qué hiciste, qué falta, SHA del último push).
  Al terminar, última línea: `FIN-<ID> <sha>`.

## Horario (ET)
- 13:30 arrancan M1..M9.
- 15:30 checkpoint: M1 entrega simulate/verify_action con tests; los demás integran contra M1.
- 17:15 congelamiento de código. 17:15–18:00 integra el orquestador en `frontier`, CI, despliegue con tag sin tráfico.
- 18:00–19:15 grabación y montaje del video.
- 19:30 decisión: si no está a la altura, se queda el envío actual tal cual.
- 20:15 envío actualizado (lo confirma Juan). 21:00 cierre.
