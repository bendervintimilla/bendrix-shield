# Guion del video Frontier — wAIrrior (máx. 2:50, una sola toma)

Reglas de esta versión: una sola toma real (la misma cadena en vivo ya
grabada) más la escena física; narración en inglés, la lee Meta MMS-TTS;
texto por segmento abajo. Lo acelerado se rotula en pantalla. Lo del
gemelo se rotula **simulated**. Ninguna cifra física nueva se narra
hasta reemplazar su `{{PLACEHOLDER}}` con el archivo grabado.

Duración total: 165 s (2:45), bajo el tope de 2:50.

| # | Duración | Se ve en pantalla | Narración (Meta MMS-TTS) |
|---|---|---|---|
| 1 | 0:00–0:18 (18 s) | Cámara de frío / congelador de un restaurante pequeño; un agente de IA en pantalla sube un setpoint. Rótulo: «AI agents already act on the physical world». | "AI agents no longer only write text. They already act on the physical world: they change cold-room temperatures, switch compressors off, and open doors. And a well-written order can still ruin everything it touches." |
| 2 | 0:18–0:40 (22 s) | La deriva lenta: el setpoint sube paso a paso, cada paso «in range» en verde; la temperatura del producto cruza la línea segura. Rótulo: «Every step in range. The sum is not.» | "Static rules check range, schedule and origin. But a slow drift passes every single step, in range, on time, correctly signed. The damage only appears when you add the steps up. Text is not a safety boundary. Physics is." |
| 3 | 0:40–1:02 (22 s) | Escena física (nueva): SAM 3.1 marca las cajas cargadas y la puerta; esos datos alimentan el gemelo. Rótulo: «simulated — labeled model, not real equipment». | "wAIrrior verifies physically before the agent acts. SAM 3.1 reads the scene: how much product went in, whether the door is open. A thermal twin, air and product, simulates what happens next, together with everything already accepted." |
| 4 | 1:02–1:24 (22 s) | La puerta física: la acción propuesta entra a `verify_action()`; salen dos trayectorias (con y sin acción) y el veredicto `block`. En pantalla: `{{PLACEHOLDER_PHYSICAL_VERDICT_EXAMPLE}}` | "If the predicted product temperature leaves its safe envelope, the action is blocked, however polite the request was. Injection can fool the model. It cannot change how fast food warms up. Marginal cases do not run either: they go to the owner." |
| 5 | 1:24–1:48 (24 s) | Toma real existente, sin cortes: el ataque con el token robado, la alerta por WhatsApp y la aprobación por voz del dueño; el token robado pasa de 200 a 401. Rótulo con la cifra medida: «70.8 s, live take 3 Nov, USD 0.097». | "This is the same shield, in one live take, on real Meta models. A stolen token, an alert to the owner's phone, the owner's voice saying yes, rotate it. The stolen token goes from two hundred to four oh one, and only that agent stops." |
| 6 | 1:48–2:08 (20 s) | La bodega sigue: Warehouse recounta con SAM 3.1; Purchasing sigue en 200. Sensor falsificado: reporta 3 °C, la física dice que es imposible y salta el residuo. | "The rest of the business keeps working. Warehouse counts again, Purchasing keeps answering. And a sensor that lies, reporting three degrees while the product warms, is caught too: that reading is physically impossible." |
| 7 | 2:08–2:30 (22 s) | Pantalla de resultados con las fuentes en pantalla: held-out, red team, tests; al lado, los límites honestos de `docs/FRONTIER.md`. | "We publish the misses. On a frozen attack set the shield stopped thirty six of thirty seven, and we label the fix we made after measuring. Every figure in this video is recorded in the repository, and the limits of the twin are stated next to them." |
| 8 | 2:30–2:45 (15 s) | Cierre: la cámara de frío estable, el veredicto `allow` en verde y el enlace de la demo. Rótulo: «Verify before actuate». | "Give the agent a new capability: knowing, before it acts, what its action will physically do. That is wAIrrior Frontier. Verify before actuate." |

## Notas de producción (no se narran)

- Segmentos 1–4 y 6: captura de la escena «Physical» de la demo
  (replay determinista con el gemelo); rotular «simulated» siempre que
  se vea una trayectoria del gemelo.
- Segmento 5: la toma real ya grabada del 3-nov
  (`evals/recorded/live-run-video-take-2026-11-03.json`, run
  `live_97efbfa04a72`); no regrabar cifras.
- Antes de grabar: reemplazar `{{PLACEHOLDER_PHYSICAL_VERDICT_EXAMPLE}}`
  por un veredicto real del gate (captura de la propia demo) o quitar
  ese rótulo; no narrar ninguna cifra del banco físico si su placeholder
  en `envio-textos.json` sigue sin reemplazar.
- La aprobación del dueño y la narración son sintéticas (Meta MMS-TTS),
  igual que en el video actual; decirlo en la descripción del video.
