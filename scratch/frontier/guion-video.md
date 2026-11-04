# Guion del video Frontier — wAIrrior (máx. 2:50, una sola toma)

Reglas de esta versión: una sola toma real (la misma cadena en vivo ya
grabada) más la escena física; narración en inglés, la lee Meta MMS-TTS;
texto por segmento abajo. Lo acelerado se rotula en pantalla. Lo del
gemelo se rotula **simulated**. Ninguna cifra se narra sin su archivo
grabado en el repo (banco y red team físicos en `evals/physical/`,
corridas en `evals/recorded/`).

Duración total: 168 s (2:48), bajo el tope de 2:50.

| # | Duración | Se ve en pantalla | Narración (Meta MMS-TTS) |
|---|---|---|---|
| 1 | 0:00–0:20 (20 s) | Titular: «wAIrrior — the AI warrior». Titulares reales de esta semana (fuentes en pantalla: Tom's Hardware, CBS, Al Jazeera): congeladores de supermercado en deshielo remoto. | "This week, attackers remotely switched supermarket freezers into defrost across Europe. A defrost is a legitimate command. Static rules let it pass. wAIrrior is the AI warrior that watches every app and machine your business runs, spots irregularities, and contains the attack on its own." |
| 2 | 0:20–0:42 (22 s) | Escena física: una cámara de frío; el setpoint deriva paso a paso, cada paso «in range» en verde; la temperatura del producto cruza la línea segura. Rótulo: «Every step in range. The sum is not.» | "Contain first, ask later. Anything reversible, wAIrrior does on its own, in seconds. Anything irreversible waits for the owner. Because an order can be in range, on schedule and correctly signed, and still ruin the product, one step at a time." |
| 3 | 0:42–1:04 (22 s) | Escena física: SAM 3.1 marca las cajas cargadas; el gemelo recibe masa térmica y simula con y sin la acción. Rótulo: «simulated — labeled model, not real equipment». | "Before an agent acts on a machine, wAIrrior verifies physically. SAM 3.1 reads the scene. A thermal twin, air and product, simulates the action together with everything already accepted. The verdict depends on physics, not on the text that convinced the agent." |
| 4 | 1:04–1:26 (22 s) | Contención automática: la acción maligna (apagado / deshielo largo) sale `block`, el equipo queda en su último estado seguro y **después** llega el aviso al dueño: «You were attacked. We already blocked it. Tap to undo.» En pantalla: veredicto real de la corrida del 4-nov, `block`, rupture at 92 min simulated. | "When the predicted product temperature leaves its safe envelope, wAIrrior blocks it alone. Nobody waits for the owner. The machine stays in its last safe state, and only then does the owner hear: you were attacked, we already blocked it, tap to undo." |
| 5 | 1:26–1:50 (24 s) | Toma real existente, sin cortes: token robado, alerta por WhatsApp y aprobación por voz del dueño; el token robado pasa de 200 a 401. Rótulo: «70.8 s, live take 3 Nov, USD 0.097 — owner approval, for the irreversible step». | "This is one live take, on real Meta models. A stolen token, and the one irreversible step, rotating it, waits for the owner's voice. The stolen token goes from two hundred to four oh one, and only that agent stops. The rest of the business keeps working." |
| 6 | 1:50–2:12 (22 s) | Warehouse recounta con SAM 3.1; Purchasing sigue en 200. Sensor falsificado: reporta 3 °C y el residuo físico lo marca imposible. | "Warehouse counts again with SAM. Purchasing never stopped. And a sensor that lies, reporting three degrees while the product warms, is caught the same way: that reading is physically impossible, so wAIrrior does not believe it." |
| 7 | 2:12–2:33 (21 s) | Resultados con fuentes en pantalla: banco físico 20/20 (simulated), red team físico con sus 3 bypass, red team de documentos 36/37, límites honestos de `docs/FRONTIER.md`. | "We publish the misses. On frozen simulated cases the physical shield stopped twenty of twenty attacks, and our own red team still found three ways past it, deferred beyond the prediction horizon. They are in the repository, next to the limits of the model." |
| 8 | 2:33–2:48 (15 s) | Cierre: cámara estable, `allow` en verde, enlace de la demo. Rótulo: «Contain first, ask later». | "Give the agent a new capability: knowing, before it acts, what its action will physically do, and containing the attack before the owner even hears about it. That is wAIrrior." |

## Notas de producción (no se narran)

- Segmentos 2–4 y 6: captura de la escena «Physical» de la demo
  (replay determinista con el gemelo, M5); rotular «simulated» siempre
  que se vea una trayectoria del gemelo. La escena debe mostrar la
  contención automática y el aviso posterior (orden del orquestador a
  M5); si la escena aún muestra aprobación previa del dueño para el
  bloqueo, no grabar el segmento 4 hasta que M5 lo actualice.
- Segmento 5: la toma real ya grabada del 3-nov
  (`evals/recorded/live-run-video-take-2026-11-03.json`, run
  `live_97efbfa04a72`); no regrabar cifras. Ahí la rotación sí esperó al
  dueño: es el paso que la regla nueva deja como «espera al dueño» solo
  si se presenta como irreversible; si M5/M10 ya muestran rotación
  automática por canario, preferir esa toma y ajustar el rótulo.
- El veredicto del segmento 4 sale de
  `evals/recorded/physical-live-2026-11-04.json` (M4): `block`, ruptura
  predicha a los 92 min, pico 8,363 °C, simulated.
- La narración y la aprobación del dueño son sintéticas (Meta MMS-TTS),
  igual que en el video actual; decirlo en la descripción del video.
- Fuentes de los titulares del segmento 1, URLs completas en
  `docs/FRONTIER.md` (sección «Por qué esta semana»).
