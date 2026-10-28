"""La forma prometida: cualquier app se conecta a Shield en 2 líneas.

El SDK `shield.wrap` llega en H3. Hoy el ejemplo corre contra la Meta Model
API con el cliente de H1, sin red si no hay llave (imprime el plan).
"""

from openai import OpenAI

import shield
from shield.meta_client import MetaClient, NeedsCredits


def main() -> None:
    # Línea 1-2 (forma final con gateway, H3):
    planned = shield  # noqa: F841  (shield.wrap llega en H3)
    client = OpenAI(base_url="https://api.meta.ai/v1", api_key="shd_demo_…")  # noqa: F841
    # Hoy: el mismo payload vía meta_client, con gate + replay + costo.
    try:
        result = MetaClient(replay_only=True).chat_completions(
            model="muse-spark-1.3",
            messages=[{"role": "user", "content": "Reply with: connected"}],
        )
        print(result.data)
    except NeedsCredits:
        print("needs_credits: sin replay guardado todavía; con llave corre igual en 2 líneas.")


if __name__ == "__main__":
    main()
