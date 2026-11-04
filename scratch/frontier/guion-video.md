# Guion Frontier — wAIrrior (2:50 máximo, una sola toma + escena Physical y Sentinel)

Formato: el que lee `~/Desktop/Hackathon-Meta/H19-video-frontier/montar.py`
(un bloque `##` por segmento, `Display`/`Spoken` en parejas; `Spoken` sin
cifras, van escritas con letras porque lo lee Meta MMS-TTS). Duración
estimada por segmento indicada en cada título; total 2:48. Cifras en
pantalla (`Display`/`Tarjeta`) solo con archivo fuente en el repo;
lo acelerado va con `Velocidad` y se rotula replay.

## S01 Gancho tres ataques (0:00-0:22)
Tipo: card
Tarjeta: [86] Three real attacks. One week.
Tarjeta: [44] Sources: Tom's Hardware · CBS · Al Jazeera · Euronews
Display: 2 Nov: supermarket freezers across Europe forced into defrost remotely, up to 50 °C. 4 Nov: a bank suspended transfers for every client. October: our own AI keys abused for ~16 hours.
Spoken: this week, attackers remotely forced supermarket freezers into defrost across Europe. days later, a bank suspended transfers for every single client. and in October, our own AI keys were abused for hours. three attacks, one missing capability.

## S02 Tesis (0:22-0:40)
Tipo: card
Tarjeta: [96] wAIrrior
Tarjeta: [50] Contain first, ask later.
Display: wAIrrior: the AI warrior that watches every app and machine your business runs, spots irregularities, and contains the attack on its own.
Spoken: wAIrrior is the AI warrior that watches every app and machine your business runs. it spots irregularities, and it contains the attack on its own. contain first, ask later.

## S03 Sentinel contiene la ola (0:40-1:08)
Tipo: panel
Rango: loaded..contain_done
Velocidad: 6
Tag: REPLAY · Sentinel · combined wave
ColorTag: amber
Display: Sentinel (replay): the combined wave hits cold room, payments and the AI gateway at once. Each app is contained on its own; human payments to known suppliers keep working. Then WhatsApp: "You were attacked. We already did X, Y, Z. Tap to undo."
Spoken: this is Sentinel. one timeline for every connected app and machine. a combined wave arrives, and each app is contained on its own, while normal work keeps going. only then does the owner get the message: you were attacked, we already handled it, tap to undo.

## S04 Physical la fisica decide (1:08-1:36)
Tipo: panel
Rango: physical_start..physical_done
Velocidad: 4
Tag: SIMULATED · Physical · thermal twin
ColorTag: blue
Display: Physical scene (simulated): SAM 3.1 reads boxes and the open door; the thermal twin predicts product temperature with and without the action. "Defrost 4 h, door open" (the real 2 Nov pattern): block, breach would arrive at 45 min, peak 16.4 °C. The machine stays at its last safe state.
Spoken: text is not a security boundary. a defrost is a legitimate command. so before the agent acts, a thermal twin predicts what the product will do. if the trajectory breaks the safe envelope, the action is blocked alone, and the machine stays at its last safe state.

## S05 Cifras (1:36-2:02)
Tipo: card
Tarjeta: [64] 1,000 scenarios: 419/419 damaging actions stopped
Tarjeta: [42] Arkéa pattern: 263/300 legitimate writes stay alive vs 0/300 suspending everything · sources in repo
Display: Simulated, frozen first, published with the misses: 1,000 scenarios, predictive 419/419 vs static 7/419; three red-team rounds, every bypass published and closed; Arkéa pattern 263/300 legitimate writes alive vs 0/300.
Spoken: we froze the cases before measuring, and we publish the misses. across a thousand simulated scenarios, the predictive shield stopped every damaging action, while static rules stopped almost none. our own red team found real bypasses in three rounds. every one is published, and every one was closed.

## S06 Modelos de Meta en vivo (2:02-2:30)
Tipo: panel
Rango: attack_done..end
Velocidad: 6
Tag: LIVE · recorded 3-4 Nov · Meta models
ColorTag: green
Display: Real Meta runs, recorded: Muse Spark controller refused the injected defrost document; Spark also generated the attack plans and wrote the incident triage. SAM 3.1 counted 7/7 boxes and saw the open door. On 3 Nov the owner's WhatsApp voice note approved the rotation: stolen token 200 → 401 in 70.8 s, USD 0.097.
Spoken: every model here is Meta, in recorded real runs. Spark refused the injected document, and Spark also played the attacker. SAM gave the twin its eyes. and the owner's own voice, transcribed by Muse Voice, approved the one irreversible step.

## S07 Cierre (2:30-2:48)
Tipo: card
Tarjeta: [92] Verify before actuate.
Tarjeta: [46] Contain first, ask later. — wAIrrior
Display: Give the agent a new capability: knowing, before it acts, what its action will physically do. wAIrrior. Demo: bendrix-shield panel (replay, no sign-in).
Spoken: give the agent a new capability. knowing, before it acts, what its action will physically do. that is wAIrrior. contain first, ask later.

## Notas de producción (no se narran; montar.py ignora este bloque sin Tipo)

- Fuentes de pantalla S01: URLs completas en `docs/FRONTIER.md`
  («Por qué esta semana»). Los 118 M€ de Arkéa son cifra de prensa no
  confirmada por el banco: si se muestra, rotularla así.
- S03: replay de la escena Sentinel (`web/sentinel_scene.py`); si la
  captura usa la toma Bodega, ajustar el `Rango` a los eventos de esa
  corrida. El aviso de WhatsApp en pantalla es el texto real de
  `evals/autopilot/REPORT.md` (ola combinada).
- S04: escena Physical de M5; rotular «simulated» siempre que se vea la
  trayectoria. Veredicto de pantalla: `block` a los 45 min, pico
  16,4 °C, de `evals/recorded/physical-live-2026-11-04-defrost-r2.json`.
- S06: toma real del 3-nov (`live_97efbfa04a72`) más rótulos de las
  corridas del 4-nov (controlador Spark, triage Spark USD 0,014644 en
  `evals/recorded/autopilot-spark-triage-2026-11-04.json`, SAM puerta y
  cajas). La narración y la voz del dueño son sintéticas (Meta MMS-TTS);
  decirlo en la descripción del video.
