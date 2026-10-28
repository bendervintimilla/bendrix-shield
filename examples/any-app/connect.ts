// Cualquier app (TS) se conecta a Shield en 2 líneas: cambia baseURL y usa tu token Shield.
// Hoy apunta a la Meta Model API; con el gateway de H3 solo cambia la URL.
import OpenAI from "openai";

const client = new OpenAI({ baseURL: "https://api.meta.ai/v1", apiKey: process.env.SHIELD_TOKEN ?? "shd_demo_…" });

const res = await client.chat.completions.create({
  model: "muse-spark-1.3",
  messages: [{ role: "user", content: "Reply with: connected" }],
});
console.log(res.choices[0]?.message?.content);
