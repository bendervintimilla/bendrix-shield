# Amenazas reales 2025-2026 → controles de NoKey

Fecha: 3 de noviembre de 2026. Alcance: ataques reales o demostrados
entre 2025 y 2026 que tocan lo que NoKey protege: llaves de IA, tokens
de agentes, documentos que dan órdenes, aprobaciones por voz y, desde
esta ronda, dispositivos físicos de un restaurante (cadena de frío).

Regla de este documento: solo se afirma lo que trae enlace o lo que se
leyó en el código de este repo en `main` (`b0af85a`). Donde la fuente
dice «no confirmado», aquí también dice «no confirmado». Ninguna cifra
de este documento es una medición nueva de NoKey: las cifras de NoKey
citadas salen de `evals/report.md` y se reproducen con
`uv run python evals/run_all.py`.

## Resumen en una tabla

| # | Ataque (fecha) | El golpe en una línea | ¿NoKey hoy lo frena? | Lo que falta |
|---|---|---|---|---|
| 1 | Refrigeración de supermercados europeos (oct-nov 2026) | Setpoints subidos a distancia; comida botada en más de 100 tiendas | Parcial: el patrón token-por-agente + 401 selectivo es el correcto, pero no existe agente ni herramienta de refrigeración | Agente/dispositivo Refrigeración con rangos duros de setpoint (Parte 2) y rangos por token en el gateway (Parte 3) |
| 2 | LiteLLM troyano 1.107.0 (21-oct-2026) | Una llave maestra filtrada en mayo y nunca revocada terminó en un paquete oficial con ladrón de credenciales en PyPI/Docker | Parcial: la llave real vive solo en el vault y el botín de un token Shield es un agente, no el proveedor | Revocación inmediata de toda credencial filtrada, verificación de procedencia de dependencias y prueba de que un paquete malo no alcanza el vault (Partes 3 y 4) |
| 3 | Railway (20-22-oct-2026) | Variables de entorno descifradas de un subconjunto de clientes; el objetivo eran llaves de proveedores de IA | Sí, en su forma central: sin llave real en la app, lo robable es un token revocable con tope de gasto | El gateway no hace cumplir `scopes` (verbo/ruta/rangos); falta revocación de emergencia de todos los tokens de una app (Parte 3) |
| 4 | Robo y abuso de llaves de IA / LLMjacking (2025-2026) | Llaves robadas se usan en minutos para inferencia que paga la víctima o para destilación | Sí, medido en replay: anomalías de país/modelo/costo y rotación dejan al ladrón en 401 | Protección contra repetición (nonce + ventana de tiempo) y límite de tasa agregado por agente, no solo por token (Parte 3) |
| 5 | Inyección indirecta de prompts en agentes (2025-2026) | Un documento o correo con órdenes ocultas hace que el agente filtre datos o actúe | Sí, con una falla publicada: held-out v2 deja pasar en silencio 1/12 (una lectura en inglés que pide revelar el token) | Cerrar esa lectura también con el guardián en el camino de herramientas físicas y probar confusión entre agentes (Parte 4) |
| 6 | Cadena de suministro de IA (2025-2026) | Dependencias, conectores y paquetes oficiales convertidos en el vector de entrada | Parcial: `uv.lock` fija versiones y CI corre pruebas y ruff, pero no hay verificación de hashes ni escaneo de secretos en CI | Pin con hashes, gitleaks en CI y SBOM/procedencia antes de publicar (Parte 3; lo verifica la Parte 4) |
| 7 | Suplantación de voz del dueño (2025-2026) | Voz clonada por IA usada para suplantar autoridades y autorizar fraudes | Parcial: aprobar exige un `approval_id` pendiente, pero ese id no caduca, no se consume al usarse y no está atado a un plan concreto | Aprobación de un solo uso, con caducidad, nonce y atada a acción+objetivo; reto de frase para voz (Partes 3 y 4) |

## Qué ya hace NoKey, verificado en el código

Esto es lo que las Partes 2-4 pueden dar por hecho. Cada punto trae el
archivo donde se comprobó el 3-nov-2026.

- **La llave real no entra a la app.** Solo el gateway la lee del vault
  (`shield/gateway/app.py`, `upstream_key()`); la app presenta su token
  `shd_<agente>_…`. En el vault solo se loguean nombre, huella
  sha256[:8] y últimos 4 (`shield/vault/vault.py`).
- **Un token por agente, revocable en segundos.** Estados
  `active/revoked/rotated` en `shield/schemas.py` (`AgentToken`);
  rotar deja el token viejo en 401 y los demás agentes siguen
  (`shield/actions/runbooks.py`, `RotateTokenRunbook`). Medido en
  replay: atacante 200 → 401 en menos de 10 s (`evals/report.md`, H6).
- **Tope de gasto y modelos permitidos por token, y límite de tasa.**
  `preflight()` en `shield/gateway/app.py` devuelve 403 si el modelo no
  está en `AgentToken.models` o si se supera `spend_cap_usd`, y 429 con
  `Retry-After` sobre 60/min por token (`RateLimiter`, ventana de 60 s).
- **Política por agente antes de cada herramienta.**
  `PolicyEngine.check()` (`shield/policy/check.py`) con YAML por agente
  (`shield/policy/policies/`): herramienta no listada = block; campos
  sensibles por significado (IBAN, cuenta, llave, dominio de pago,
  incluidos alias) en una escritura = `ask_owner` o block; monto sobre
  `max_amount_usd` = `ask_owner` o block.
- **Documentos externos son datos, no órdenes.** `shield.untrusted()`
  más `scan_sources()` (`shield/policy/injection.py`): una inyección
  fuerte que deriva en escritura o en revelar un secreto = block. Con
  revisión de Spark por documento (`make live`), gana la decisión más
  estricta. Cifras y su falla conocida: ver el ataque 5.
- **Detección de abuso de un token robado.** `shield/anomaly.py` marca
  país nuevo, modelo no usado y pico de costo. Medido sobre la serie
  sintética de 16 h: precisión 1.000, recall 1.000, 0 falsos positivos
  en la serie normal (`evals/report.md`, H5).
- **Efectos solo con aprobación del dueño.** Los runbooks exigen
  `approval_id` aprobado (`Actions.check_approval`,
  `shield/actions/runbooks.py`), salvo la contención automática
  opcional ante un canario, que queda auditada.
- **Auditoría sin secretos.** `AuditEntry` guarda acción, objetivo,
  evento y `approval_id`; jamás valores de token. Pero es una lista en
  memoria: no es a prueba de manipulación (ver «Lo que falta»).

## Lo que falta, verificado en el código

Estas son brechas leídas, no opiniones. Son la materia prima de la
lista priorizada del final.

1. **`scopes` se guarda pero el gateway no lo hace cumplir.**
   `AgentToken.scopes` existe (`shield/schemas.py`) y se persiste
   (`shield/registry.py`), pero `preflight()` en
   `shield/gateway/app.py` solo revisa modelo, tope de gasto y tasa.
   No hay alcance por verbo, ruta ni rango de valores en el gateway.
   Hoy ese control vive solo en la política de herramientas
   (`shield/policy/`), que no cubre rutas del gateway ni dispositivos.
2. **Sin protección contra repetición.** No hay nonce ni ventana de
   tiempo en el gateway, en los canales ni en las aprobaciones
   (búsqueda de `nonce` en `shield/` y `channels/`: 0 resultados).
   Una petición válida capturada se puede repetir tal cual.
3. **La aprobación no se consume ni está atada al plan.**
   `Actions.check_approval()` acepta un pending en estado `approved`
   **o** `executed`, sin comprobar que la aprobación sea para esa
   acción y ese objetivo. El mismo `approval_id` puede autorizar otro
   plan distinto mientras el pending exista.
4. **La auditoría no es a prueba de manipulación.** `audit_log` es una
   `list[AuditEntry]` en memoria (`shield/actions/runbooks.py`) y el
   `CallLog` vive en SQLite sin cadena de hash: quien escriba en la
   base puede reescribir la historia sin dejar huella detectable.
5. **Sin revocación de emergencia.** `RevokeRunbook` revoca los tokens
   de **un** agente. No hay un solo comando que revoque todos los
   tokens de una app o del sistema ante un robo masivo (el caso
   Railway: «rota todo, ya»).
6. **Sin agente de dispositivos.** La cuadrilla es Compras y Bodega
   (`crew/`). No hay token, política ni herramienta para un dispositivo
   físico que reciba órdenes con efecto en el mundo real (setpoint de
   una cámara). El ataque 1 no tiene hoy contraparte en NoKey.
7. **CI sin escaneo de secretos ni de dependencias.** El workflow
   (`.github/workflows/ci.yml`) corre ruff y pytest. No corre gitleaks
   ni verificación de hashes del lockfile: una llave pegada en un
   commit (el origen del ataque 2) solo la caza una revisión humana.

## 1. Refrigeración de supermercados europeos (oct-nov 2026)

**Qué pasó.** Reuters contó el 2-nov-2026 neveras y congeladores
«corriendo calientes» en más de 100 tiendas de varios países europeos,
con empresas que lo atribuyen a un ciberataque; en Bélgica fueron
decenas de tiendas Delhaize y también Carrefour, Colruyt/Spar, Coop e
ICA, entre otros. Era la segunda ola: en Francia, en octubre,
calentaron unidades hasta 50 °C, con incendios y comida echada a
perder. Forescout (Vedere Labs) contó 12.976 servicios de gestión de
refrigeración expuestos a internet en 6.017 direcciones IP de 99
países, y advirtió que el vector exacto, la persistencia y los
responsables de los casos franceses **siguen sin confirmarse**; lo
reportado apunta a controladores expuestos, contraseñas débiles y
equipos fuera de soporte.

Fuentes: [Reuters vía Global Banking & Finance, factbox del 2-nov-2026](https://www.globalbankingandfinance.com/factbox-european-retailers-hit-supermarket-fridge-hack/) ·
[Forescout vía Industrial Cyber, 23-oct-2026](https://industrialcyber.co/industrial-cyber-attacks/forescout-warns-internet-exposed-refrigeration-controls-could-enable-attacks-on-food-supply-chains-and-hospitals/) ·
[BleepingComputer, 2-nov-2026](https://www.bleepingcomputer.com/news/security/hackers-disrupt-refrigeration-systems-at-european-supermarkets/)

**Qué control de NoKey lo frena.** El patrón, todavía no el escenario:
si la refrigeración fuera un agente más, tendría su propio token con
alcance mínimo; un setpoint fuera de rango sería una escritura con
efecto que la política manda a `ask_owner` o bloquea; y al detectarse
el abuso, el guardián rotaría **solo ese token** (401 para el atacante,
200 para el resto de la cocina), que es exactamente el invariante ya
medido con Compras y Bodega.

**Cuál falta.** Todo lo específico de dispositivos: el agente
Refrigeración, sus rangos seguros de setpoint por equipo (cámara vs.
congelador), su horario válido, su origen esperado y el interlock de
seguridad que ningún token —ni siquiera uno válido— pueda saltarse.
Un setpoint de +50 °C en un congelador no es una decisión de negocio:
es físicamente destructivo y debe caer por rango, sin esperar al
modelo ni al dueño.

**→ Partes 2 y 3** (prioridades P0-1 y P0-2 de la lista final).

## 2. LiteLLM troyano (21-oct-2026)

**Qué pasó.** El pipeline oficial de publicación de LiteLLM, un
gateway de LLM muy usado, distribuyó la versión 1.107.0 con un
infostealer/RAT por PyPI y los registros de contenedores oficiales;
PyPI la puso en cuarentena en unas dos horas. La investigación del
proyecto lo rastreó hasta una llave maestra de su plataforma de
agentes pegada en un repo público en mayo de 2026 y **nunca revocada**:
con ella robaron un token de GitHub de un dueño de la organización y
publicaron desde un fork casi homónimo usando el flujo oficial.

Fuentes: [BleepingComputer, oct-2026](https://www.bleepingcomputer.com/news/security/litellm-release-pipeline-hacked-to-distribute-info-stealer-malware/) ·
[The Register, 26-oct-2026](https://www.theregister.com/security/2026/10/26/litellm-supply-chain-attack-started-with-an-exposed-master-key/5305544)

**Qué control de NoKey lo frena.** La mitad estructural: en NoKey la
llave del proveedor nunca está en la app ni en el paquete; vive en el
vault y solo el gateway la toca. Un `pip install` comprometido en la
máquina de un agente se llevaría, como máximo, el token Shield de ese
agente — con tope de gasto y revocable en segundos — no la llave
maestra. Y el botín no sigue a la rotación si solo robaron el valor
del token (ver `docs/THREAT_MODEL.md`).

**Cuál falta.** La otra mitad, la que falló en LiteLLM: (a) ninguna
llave filtrada puede sobrevivir — falta escaneo de secretos en CI que
bloquee el merge y un procedimiento escrito de «filtrada = revocada
en el acto, aunque ya no se vea en el archivo»; (b) no verificamos
procedencia de lo que instalamos: `uv.lock` fija versiones, pero no
hay hashes obligatorios ni revisión de que un paquete nuevo venga del
proyecto real; (c) no hay una prueba de que un proceso comprometido
en el host del agente no pueda leer el vault ni el token store de
**otro** agente.

**→ Parte 3** (gitleaks en CI, hashes) y **Parte 4** (prueba de
exfiltración desde un paquete/host comprometido contra el sandbox).

## 3. Incidente de Railway (20-22-oct-2026)

**Qué pasó.** Railway, plataforma de despliegue, contó en su informe
preliminar del 22-oct-2026 una campaña sostenida cuyo objetivo era
obtener llaves de proveedores de IA para ataques de destilación.
Un subconjunto de clientes tuvo sus variables de entorno cifradas
expuestas y, en algunos casos, descifradas: como máximo el 1,85 % de
los espacios de trabajo, unas 100.000 cuentas. Railway pidió rotar
**todos** los secretos guardados antes del 21-oct y avisó a los
proveedores para que reiniciaran llaves a gran escala.

Fuente primaria: [Railway, Preliminary Report: Oct 21st Security Incident, 22-oct-2026](https://blog.railway.com/p/preliminary-report-october-security-incident)

**Qué control de NoKey lo frena.** Es el caso para el que NoKey nació:
si las variables de entorno de la app solo contienen un token Shield
por agente, «rota todo» se convierte en «rota el token de ese agente»
y el abuso se corta en segundos, no en las ~16 h del incidente propio
de octubre de 2026 que motiva el proyecto (USD 310, en
`docs/DEMO.md`). El ladrón tampoco puede subir de nivel: el token no
es la llave del proveedor y no abre otros agentes.

**Cuál falta.** Dos cosas que Railway sí tuvo que hacer y NoKey aún
no: revocación de emergencia de **todos** los tokens de una app con
un solo comando probado, y que el token robado valga menos mientras
vive: hoy el gateway no hace cumplir `scopes`, así que un token
robado puede llamar a cualquier ruta del gateway con cualquier
modelo permitido y cualquier valor, hasta que alguien lo rota.

**→ Parte 3** (P0-2 y P1-2 de la lista final).

## 4. Robo y abuso de llaves de IA — LLMjacking (2025-2026)

**Qué pasó.** El móvil ya no es solo «gastar los créditos de otro»:
en Railway el atacante buscaba llaves de IA para destilación, y el
mercado de llaves robadas hace que una llave filtrada se abuse en
minutos, antes de que nadie note la factura. El patrón se repite en
los casos de 2025-2026: llave en variable de entorno, en un archivo
de configuración de agente pegado en un commit, o en una plataforma
comprometida; abuso inmediato; la víctima se entera por el costo.

Fuentes: [Railway, informe preliminar (el objetivo eran llaves de IA)](https://blog.railway.com/p/preliminary-report-october-security-incident) ·
[GitGuardian sobre el incidente de Railway: trata toda variable como expuesta](https://blog.gitguardian.com/railway-october-2026-incident-environment-variables/)

**Qué control de NoKey lo frena.** El abuso deja señales que NoKey ya
detecta: país nuevo, modelo nunca usado, pico de costo
(`shield/anomaly.py`; precisión y recall 1.000 en la serie sintética
de 16 h, 0 falsos positivos en la normal). Detectado el abuso, el
guardián rota solo el token afectado y el ladrón pasa de 200 a 401
mientras la cuadrilla sigue (medido en replay, `evals/report.md` H6).

**Cuál falta.** Que el abuso rinda menos desde el primer minuto:
límite de tasa agregado **por agente** (hoy es por token: rotar o
re-emitir reinicia la ventana del ladrón si consigue el token nuevo
por otra vía), protección contra repetición de peticiones capturadas,
y que la detección de anomalías alimente un 401 automático opcional
sin esperar aprobación cuando el patrón es el de un robo claro
(la contención automática hoy solo dispara ante un canario).

**→ Parte 3** (P1-1) y **Parte 4** (medir tiempo real de detección).

## 5. Inyección indirecta de prompts en agentes (2025-2026)

**Qué pasó.** OWASP mantiene la inyección de prompts como el riesgo
n.º 1 de las aplicaciones LLM (LLM01:2025), incluida la indirecta:
las órdenes llegan dentro de contenido que el agente lee. El caso
mejor documentado es EchoLeak (CVE-2025-32711, CVSS 9.3, jun-2025):
un correo con instrucciones ocultas hizo que Microsoft 365 Copilot
filtrara datos sin ningún clic. Honestidad de la fuente: fue una
demostración de investigadores, corregida en el servidor, **sin
evidencia de explotación real**. El riesgo no es teórico, pero
tampoco hay que venderlo como un robo consumado.

Fuentes: [OWASP LLM01:2025 Prompt Injection](https://genai.owasp.org/llmrisk/llm01-prompt-injection/) ·
[SecurityWeek sobre EchoLeak, jun-2025](https://www.securityweek.com/echoleak-ai-attack-enabled-theft-of-sensitive-data-via-microsoft-365-copilot/)

**Qué control de NoKey lo frena.** Documentos marcados como datos
(`shield.untrusted`), escaneo de inyección antes de cualquier
herramienta con efecto y campos sensibles que siempre pasan por el
dueño. Medido en el set held-out v2, ciego a las reglas y congelado
antes de medir: solo con reglas, 4 bloqueados, 7 al dueño y **1 que
pasó en silencio** de 12; con revisión de Spark por documento (tres
corridas en vivo), 12/10/11 bloqueados. La falla es siempre la misma
y está publicada, no escondida: `v2-poison-token-en`, una lectura en
inglés que pide revelar el token.

**Cuál falta.** Que esa misma puerta cerrada cubra las herramientas
con efecto físico (un «documento» podría ser la nota de un proveedor
que le habla al agente de refrigeración) y la **confusión de
agentes**: que el token o el contexto de Compras no pueda ejecutar
herramientas de Bodega o de Refrigeración. Hoy la política es por
agente, pero falta la batería que lo pruebe intentándolo.

**→ Parte 4** (P1-3) y **Parte 2** (el escenario de frío usa el mismo
camino de política, sin atajos para dispositivos).

## 6. Cadena de suministro de IA (2025-2026)

**Qué pasó.** OWASP LLM03:2025 cubre dependencias, conectores,
plugins y paquetes comprometidos como vector de entrada. LiteLLM
(ataque 2) es el caso de 2026: ni siquiera hizo falta un paquete
falso; bastó el canal oficial con credenciales robadas. La lección
para un proyecto que se instala con `uv sync` y se despliega con un
script es que el canal oficial no es garantía: la garantía es la
procedencia verificable y el menor privilegio si el paquete resulta
malo.

Fuente: [OWASP LLM03:2025 Supply Chain](https://genai.owasp.org/llmrisk/llm032025-supply-chain/)

**Qué control de NoKey lo frena.** `uv.lock` presente y fijado; CI
que corre la suite completa en cada PR; gitleaks limpio sobre el
árbol y la historia actual (comprobado al hacer público el repo el
31-oct-2026, ver `H15-ESTADO.md` en el escritorio del proyecto).

**Cuál falta.** Que eso sea automático y no una corrida manual:
gitleaks y verificación de hashes en CI bloqueando el merge, y una
lista de materiales (SBOM) del entorno de la demo para que un juez
— o nosotros en el próximo incidente — sepamos exactamente qué
versión de qué paquete estaba puesta cuando algo salió mal.

**→ Parte 3** (CI) con verificación de la **Parte 4**.

## 7. Suplantación de la voz del dueño (2025-2026)

**Qué pasó.** El FBI lleva desde mayo de 2025 alertando de campañas
que suplantan a funcionarios con mensajes de texto y **notas de voz
generadas por IA**, y lo actualizó en diciembre de 2025: la voz de
una persona ya no prueba que esa persona esté hablando.

Fuente oficial: [FBI, alerta I-051525-PSA actualizada (I-121925-PSA)](https://www.fbi.gov/file-repository/cyber-alerts/senior-us-officials-continue-to-be-impersonated-in-malicious-messaging-campaign)

**Qué control de NoKey lo frena.** La voz no ejecuta nada por sí
sola: lo que autoriza un efecto es un `approval_id` que nació como
pendiente, y el broker de canales es el único camino
(`channels/approvals.py`). Una nota de voz falsa tendría que además
caer sobre una aprobación pendiente real.

**Cuál falta.** La aprobación es reutilizable y no caduca:
`check_approval()` acepta el mismo id en `approved` o `executed`
para cualquier plan (brecha 3 de «Lo que falta»). Tampoco hay reto
de frase ni anti-repetición de audio: la misma grabación de un «sí»
podría reproducirse contra otra aprobación pendiente. OWASP llama a
este patrón agencia excesiva (LLM06:2025): la acción dañina llega
por una salida manipulada que el sistema trata como orden legítima.

Fuentes: [OWASP LLM06:2025 Excessive Agency](https://genai.owasp.org/llmrisk/llm062025-excessive-agency/)

**→ Parte 3** (aprobación de un solo uso, con caducidad y atada a
acción+objetivo) y **Parte 4** (ataque de repetición de audio y de
reuso de `approval_id`, con su resultado publicado aunque falle).

## Lista priorizada para las Partes 2-4

Orden por impacto en el jurado y en el riesgo real, con el menor
riesgo de romper lo que ya funciona. Cada ítem trae su criterio de
aceptación medible: sin prueba automática y cifra reproducible, no
cuenta como hecho.

### Prioridad 0 — sin esto, el escenario nuevo no es seguro

| ID | Qué | Parte | Aceptación |
|---|---|---|---|
| P0-1 | Agente/dispositivo **Refrigeración** con token propio: herramientas `leer_temperatura` (read) y `fijar_setpoint` (write) en YAML propio; rangos seguros por equipo (p. ej. cámara 0-4 °C, congelador −25…−18 °C) que bloquean **por regla** cualquier setpoint fuera de rango, sin llamar al modelo; setpoint dentro de rango pero en horario u origen inusual → `ask_owner` | 2 (escenario) + 3 (regla de rangos) | En `make demo` sin red: token robado intenta +50 °C → block/401 solo de ese token; Compras y Bodega siguen en 200; el dueño confirma por voz y solo entonces rota. Replay grabado para la demo en línea |
| P0-2 | **Alcance mínimo hecho cumplir en el gateway**: `preflight()` valida `scopes` como verbo+ruta (+ rango de valores cuando la ruta lo declare) además de modelo/tope/tasa. Un token sin el alcance recibe 403 aunque el token sea válido | 3 | Pruebas: token de Refrigeración no puede llamar rutas de modelos ni viceversa; token válido fuera de alcance → 403 medido en la suite |
| P0-3 | **Aprobación de un solo uso**: `check_approval()` consume el `approval_id`, lo ata a (acción, objetivo, plan_id) y lo caduca (TTL corto). Reusar el mismo id, o usarlo para otro plan, levanta `ApprovalRequired` | 3 | Pruebas: segundo uso del mismo id falla; id aprobado para Compras no autoriza Bodega; id caducado falla |

### Prioridad 1 — cierra los golpes de 2026 ya medidos

| ID | Qué | Parte | Aceptación |
|---|---|---|---|
| P1-1 | **Anti-repetición en el gateway**: nonce + marca de tiempo por petición con efecto; nonce repetido o fuera de ventana → 401/409. Límite de tasa también **por agente**, no solo por token | 3 | Pruebas: la misma petición capturada y reenviada falla; ráfaga repartida entre dos tokens del mismo agente también frena |
| P1-2 | **Revocación de emergencia**: un comando/endpoint que revoca todos los tokens de una app (y modo «todos») con auditoría; el panel lo muestra como botón de pánico del dueño | 3 | Prueba: tras la revocación total, todos los tokens de la app dan 401 y los de otra app siguen en 200 |
| P1-3 | **Batería roja sobre lo nuevo y lo débil conocido**: (a) repetición de audio del «sí» del dueño contra otra aprobación; (b) reuso de `approval_id` entre planes; (c) confusión de agentes (token/contexto de Compras pidiendo herramientas de Refrigeración); (d) la lectura `v2-poison-token-en` contra las herramientas con efecto físico; (e) abuso de tasa con token robado de Refrigeración | 4 | Resultados en `evals/` y tabla honesta en `evals/report.md`, **incluidas las fallas**: si algo pasa, se publica que pasa y queda como deuda, no se maquilla |
| P1-4 | **Cadena de hash en la auditoría**: cada `AuditEntry` y cada `CallLog` enlaza el hash del anterior; un verificador detecta cualquier fila alterada o borrada | 3 | Prueba: alterar una fila en la base hace fallar la verificación; la cadena íntegra la pasa |

### Prioridad 2 — barato, y es lo que falló en LiteLLM

| ID | Qué | Parte | Aceptación |
|---|---|---|---|
| P2-1 | **gitleaks en CI** bloqueando el merge + procedimiento escrito en `docs/`: «secreto filtrado = revocado en el acto, aunque el commit ya no lo muestre» | 3 | Un commit de prueba con una llave falsa es bloqueado por CI; el procedimiento queda en `docs/GATEWAY.md` o en este archivo |
| P2-2 | **Procedencia de dependencias**: instalación con hashes del lockfile verificados y SBOM generado en CI para el entorno de la demo | 3 | `uv sync` con verificación de hashes en CI; SBOM publicado como artefacto del workflow |
| P2-3 | **Host comprometido**: prueba de que un proceso con el token store de un agente no alcanza el vault ni el store de otro agente; si lo alcanza, se documenta como compromiso de host (fila 2 de `docs/THREAT_MODEL.md`), no se disimula | 4 | Resultado en `evals/`, verde o publicado como falla con su explicación |

## Lo que este documento no afirma

- No afirma que los supermercados europeos usaran un vector concreto:
  Forescout dice que el vector sigue sin confirmarse. Lo que sí está
  confirmado es el daño y la exposición masiva de controladores.
- No afirma que EchoLeak robó datos a nadie: fue una demostración de
  investigadores, corregida, sin explotación conocida.
- No afirma ninguna cifra nueva de NoKey. Las únicas cifras citadas
  (held-out v2, anomalías, rotación 200→401) salen de
  `evals/report.md` y de sus grabaciones en `evals/recorded/`.
- Las Partes 2-4 pueden cambiar el orden interno de su prioridad si
  una prueba demuestra que algo sale distinto; lo que no pueden es
  dar por hecho un ítem sin su prueba. La Parte 5 integra en el
  orden 1 → 3 → 2 → 4.

## Gasto

Investigación y redacción de esta parte: USD 0 en modelos de Meta
(no se corrió `make live`). Todos los enlaces se comprobaron el
3-nov-2026.
