# SAM 3.1 en Bodega — rutas, formato y costo real

Leído de la documentación oficial el **28-oct-2026**. Nada aquí es
adivinado: cada ruta y campo sale de la página citada.

## Fuentes

- [SAM overview](https://dev.meta.ai/docs/sam/overview)
- [Media segmentation](https://dev.meta.ai/docs/media-segmentation)
- [Segmenting with prompts](https://dev.meta.ai/docs/sam/segmenting)
- [Reading segmentation output](https://dev.meta.ai/docs/sam/reading-segmentation)
- Precios: [Pricing and rate limits](https://dev.meta.ai/docs/pricing-rate-limits) (también en [docs/MODELS.md](MODELS.md))

## Ruta y pedido

- `POST /v1/responses` sobre `https://api.meta.ai/v1`, modelo `sam-3.1`.
  No hay ruta SAM separada: va por Responses, igual que en el gateway.
- Un mensaje de usuario con dos partes:
  - `input_text`: frase nominal corta que nombra **un solo concepto**
    (`"yellow school bus"`, `"glasses"`). Un concepto por pedido: para
    varios conceptos se envía un pedido por concepto. Listas con comas,
    preguntas u órdenes devuelven cero coincidencias.
  - `input_image` con `image_url`, o `input_video` con `video_url` o
    `file_id` (Files API). La URL puede ser pública o data URL base64.
- Video: contenedores MP4/MOV con H.264, H.265 o MPEG-4; hasta 15.000
  frames por pedido y hasta 16 objetos por frame.
- `stream: true` es la ruta recomendada: cada frame llega como un
  `response.output_text.delta` hasta `response.completed`. Sin streaming
  llega el mismo resultado en una sola respuesta.
- Confianza opcional: `metadata.include_confidence = "true"` (string)
  agrega `c` (0 a 1) a cada box y mask. Codificación de mask opcional:
  `metadata.mask_encoding = "one_bit"` (compacta) o `lossless` (default).

## Salida (gramática oficial)

El resultado viaja en el canal `output_text` como texto con tokens
especiales: **una línea por frame** (imagen = una sola línea `<0f>`).

```text
<0f>0<|box;x1=353;y1=382;x2=453;y2=427;w=537;h=561|><|mask;x=0;y=0;data=46,101,~...|>,1<|box;...|><|mask;...|>
```

- `<Nf>`: índice de frame, base cero, **no necesariamente contiguo ni
  ascendente**; un frame sin objetos no emite línea. Nunca asumas que la
  línea N es el frame N: lee el marcador explícito.
- El entero antes de cada box es el **ID de objeto, estable entre frames**
  en video (track ID). No es denso ni base cero garantizada: puede venir
  `0, 2`. Contar stock en video es contar IDs distintos, no sumar frames.
- Box: `x1,y1,x2,y2` en píxeles de la fuente; `w,h` = tamaño de la fuente,
  repetido en cada registro.
- Mask: `data=<H>,<W>,<enc>payload`; H = alto (filas), W = ancho
  (columnas); `<enc>` es `~` (lossless, default) o `!` (one_bit); el
  payload es **base85, no base64**, y puede contener `~` o `!`.
- Cero coincidencias es un resultado válido: stream completo con
  `output_text` vacío. No es un error.

Nuestro parser de esta gramática vive en
[crew/bodega/sam.py](../crew/bodega/sam.py) (`parse_sam_output`,
`count_from_output`): imagen cuenta registros del frame; video cuenta
track IDs únicos y reporta el conteo por frame.

## Costo real

| Medio | Precio oficial | Cómo lo calcula Shield |
|---|---|---|
| Imagen | USD 2,50 / 1.000 imágenes (= USD 0,0025 por imagen) | `SAM_USD_PER_IMAGE` por pedido (un concepto) |
| Video | USD 0,20 / 1.000 frames, **mínimo 50 frames por pedido** | `max(frames, 50) / 1000 * 0,20` |

Ejemplos: 1 imagen = USD 0,0025. Un clip corto facturado al mínimo de
50 frames = USD 0,01. Un clip de 300 frames = USD 0,06. Contar 3
conceptos son 3 pedidos: el costo se multiplica por concepto.

En este repo el costo por llamada también lo calcula
`shield/meta_client.compute_cost_usd` (`sam-3.1`: usa
`usage.video_frames_processed` si la API lo reporta; si no, una imagen).
Sin créditos (401/402/403) todo corre en replay con salidas SAM
sintéticas y el costo reportado es el teórico de esta tabla, marcado
como tal en `evals/report.md`. **No hay tomas reales de bodega todavía**.
