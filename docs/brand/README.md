# MuseShield — Business Protection · identidad ligera

**Nombre público:** MuseShield
**Subtítulo:** Business Protection
**Tagline (EN, para video y envío):** Your app never holds the real key. One leaked token, revoked in seconds.
**Tagline (ES):** Tu app nunca tiene la llave real. Un token filtrado, revocado en segundos.

Cifras que respaldan el tagline (solo `evals/report.md`, held-out v2):
0/12 escrituras sensibles en silencio · atacante 200 → 401 en <10 s en replay
frente a ~16 h del incidente real · 4/12 bloqueados y 7/12 al dueño en held-out v2
(1 lectura en inglés pasó en silencio: se dice, no se esconde).

## Aviso de marca

Built on Meta's Muse models; independent project, not affiliated with or endorsed by Meta.

«Muse» es marca de Meta. El nombre MuseShield lo eligió el equipo para el
hackathon y no implica respaldo de Meta. Si Meta o Cerebral Valley piden
otro nombre, se usan las alternativas de abajo sin tocar código ni URLs.

Revisión contra `01-REGLAS-OFICIALES.md` (H11-B-KIT, reglas leídas 29-oct):
las reglas exigen obra original, repo público, uso real de modelos Meta y
declarar lo nuevo; ninguna regla fija ni prohíbe nombres de proyecto ni
exige aprobación previa del nombre. El riesgo no es de descalificación por
una regla escrita: es de marca y de confusión (que parezca producto
oficial de Meta). Por eso el aviso de arriba va en README, envío y video.

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
- El panel web usa favicon textual «M» sobre tinta (data URI en `web/app.py`)
  y la misma paleta; no depende de archivos externos.

## Variantes de nombre (por si Juan prefiere otra, ordenadas por impacto)

1. **NoKey — Business Protection.** La promesa en el nombre: ningún agente
   tiene la llave. Es la más memorable y no usa marca de terceros.
2. **VaultGate — Business Protection.** Junta la bóveda de llaves y la
   puerta de política; suena a infraestructura seria para startups.
3. **Revoke — Business Protection.** El gesto que vende el video
   (200 → 401 en segundos); corto, pero genérico para buscarlo en la web.
