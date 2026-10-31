# NoKey — Business Protection · identidad ligera

**Nombre público por defecto:** NoKey
**Subtítulo:** Business Protection
**Tagline (EN, para video y envío):** Your app never holds the real key. One leaked token, revoked in seconds.
**Tagline (ES):** Tu app nunca tiene la llave real. Un token filtrado, revocado en segundos.

Cifras que respaldan el tagline (solo `evals/report.md`, held-out v2):
0/12 escrituras sensibles en silencio · atacante 200 → 401 en <10 s en replay
frente a ~16 h del incidente real · 4/12 bloqueados y 7/12 al dueño en held-out v2
(1 lectura en inglés pasó en silencio: se dice, no se esconde).

## Por qué NoKey

El bot de Discord del hackatón avisó el 30-oct que el nombre público no
puede usar Muse ni Meta. Juan aún no decide el nombre definitivo, así
que queda NoKey por defecto: la promesa en el nombre, ningún agente tiene
la llave, y no usa marca de terceros. Las excepciones a esa regla se
piden a up_exceptions@meta.com.

## Cómo cambiarlo (un comando)

```bash
uv run python scripts/set_brand.py NUEVO_NOMBRE          # aplica
uv run python scripts/set_brand.py NUEVO_NOMBRE --dry-run # solo muestra
```

El comando actualiza `shield/brand.py` — la única fuente de la marca en
código (`BRAND` y `SUBTITLE`; `web/brand.py` solo lo reexporta) — y
reemplaza el nombre anterior en textos no-código: `README.md`,
`pyproject.toml`, `docs/**/*.md`, `docs/brand/*.svg`,
`docs/brand/slides/*.svg`, `web/README.md` y `shield/README.md`. No toca
`evals/` ni datos medidos. Se conservan literalmente el nombre técnico
`bendrix_shield`, `bendrix-shield` y las URLs de Cloud Run.

## Aviso de no afiliación

Built on Meta's Muse models; independent project, not affiliated with or endorsed by Meta.

Ese aviso se mantiene en inglés en README, envío y video.

## Paleta

| Uso | Color | Dónde |
|---|---|---|
| Tinta / fondo oscuro | `#14201C` | Cabeceras, slide de portada |
| Verde escudo | `#1F7A4D` | Acciones, aprobado, botón principal |
| Chispa ámbar | `#E8A33D` | Onda del logo, cifra clave, 200 → 401 |
| Papel | `#EEF0EA` | Fondo del panel (el que ya usa `web/app.py`) |
| Texto | `#1C2420` | Cuerpo |
| Alerta | `#B42318` | Bloqueado / 401, solo para eso |

Tipografía: Georgia/serif para titulares (la del panel) y sistema
sans para cuerpo. Sin degradados morados, sin iconos emoji.

## Archivos

- `logo.svg` — escudo con onda/chispa ámbar. Sirve también de favicon.
- `slides/01-portada.svg` — portada del video (1920×1080).
- `slides/02-problema.svg` — Black October.
- `slides/03-cierre.svg` — resultado 200 → 401 y cifras held-out v2.
- El panel web usa favicon textual con la inicial de `BRAND` sobre tinta
  (data URI en `web/app.py`) y la misma paleta; no depende de archivos externos.

## Variantes de nombre (por si Juan prefiere otra)

1. **VaultGate — Business Protection.** Junta la bóveda de llaves y la
   puerta de política; suena a infraestructura seria para startups.
2. **Revoke — Business Protection.** El gesto que vende el video
   (200 → 401 en segundos); corto, pero genérico para buscarlo en la web.
