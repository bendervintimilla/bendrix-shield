// Cualquier app (TS) se conecta a Shield en 2 líneas.
import OpenAI from "openai";

const client = new OpenAI({
  baseURL: process.env.SHIELD_GATEWAY_URL ?? "http://127.0.0.1:8000/v1",
  apiKey: process.env.SHIELD_TOKEN ?? "shd_demo_…",
});
const res = await client.chat.completions.create({
  model: "muse-spark-1.3",
  messages: [{ role: "user", content: "Reply with: connected" }],
});
console.log(res.choices[0]?.message?.content);
