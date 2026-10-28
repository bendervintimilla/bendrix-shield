"""bendrix_shield — paquete instalable del SDK de Bendrix Shield.

from openai import OpenAI
import bendrix_shield as shield

client = shield.wrap(OpenAI(), "shd_<agente>_…")  # 1 línea y listo
"""

from shield.sdk.wrap import DEFAULT_GATEWAY_URL, gateway_url, wrap

__version__ = "0.1.0"
__all__ = ["DEFAULT_GATEWAY_URL", "gateway_url", "wrap"]
