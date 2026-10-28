"""Cualquier app se conecta a Shield en 2 líneas (Python)."""

from openai import OpenAI

import bendrix_shield as shield

client = shield.wrap(OpenAI(), "shd_demo_reemplaza-con-tu-token")
res = client.chat.completions.create(
    model="muse-spark-1.3",
    messages=[{"role": "user", "content": "Reply with: connected"}],
)
print(res.choices[0].message.content)
