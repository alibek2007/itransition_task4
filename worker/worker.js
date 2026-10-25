/**
 * Cloudflare Worker: AI chat backend for the Bookstore dashboard.
 *
 * Browser  --POST {question, store, history}-->  this Worker  --> Gemini API
 * The Gemini API key lives only here (as a Worker secret), never in the page.
 */

const ALLOWED_ORIGINS = [
  "https://alibek2007.github.io",
  "http://localhost:8000",
  "http://127.0.0.1:8000",
];

let cachedData = null;      // results.json, reused between requests
let cachedAt = 0;
const CACHE_MS = 10 * 60 * 1000;

// Used in order when the main model is busy or rate-limited.
const FALLBACK_MODELS = ["gemini-3.6-flash", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"];

// ---------- helpers ----------
function cors(origin) {
  const allowed = ALLOWED_ORIGINS.includes(origin) ? origin : ALLOWED_ORIGINS[0];
  return {
    "Access-Control-Allow-Origin": allowed,
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
  };
}

function json(body, status, origin) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...cors(origin) },
  });
}

// Turn results.json into a compact text the model can read.
// Daily revenue is large, so it is included only for the stores the question is about;
// every store gets monthly revenue instead.
function buildContext(data, detailStores) {
  return data.map((s) => {
    const monthly = {};
    for (const d of s.daily_revenue) monthly[d.date.slice(0, 7)] = (monthly[d.date.slice(0, 7)] || 0) + d.revenue;
    const monthlyText = Object.entries(monthly).map(([m, v]) => `${m}:${v.toFixed(2)}`).join(", ");
    const top5 = s.top5_days.map((d, i) => `${i + 1}. ${d.date} $${d.revenue}`).join("; ");
    const ranking = s.top_author_sets_ranking.map((a) => `${a.authors.join(" & ")} (${a.sold})`).join("; ");
    const daily = detailStores.includes(s.store)
      ? s.daily_revenue.map((d) => `${d.date}:${d.revenue}`).join(",")
      : "(not included - ask about this store to get daily figures)";
    return [
      `### ${s.store}`,
      `Date range: ${s.date_range[0]} to ${s.date_range[1]}`,
      `Total revenue: $${s.total_revenue}; orders: ${s.total_orders}; books sold: ${s.books_sold}`,
      `User records: ${s.user_records}; real unique users after reconciliation: ${s.unique_users}`,
      `Unique author sets: ${s.unique_author_sets}`,
      `Most popular author set(s): ${s.top_authors.map((a) => a.join(" & ")).join("; ")} with ${s.top_authors_sold} copies sold`,
      `Top 10 author sets by copies sold: ${ranking}`,
      `Best buyer ids (all aliases of one person): [${s.best_buyer.ids.join(", ")}], spent $${s.best_buyer.total_spent} over ${s.best_buyer.orders} orders`,
      `Top 5 days by revenue: ${top5}`,
      `Monthly revenue in USD (month:revenue): ${monthlyText}`,
      `Daily revenue in USD (date:revenue): ${daily}`,
    ].join("\n");
  }).join("\n\n");
}

async function getData(env) {
  if (cachedData && Date.now() - cachedAt < CACHE_MS) return cachedData;
  const res = await fetch(env.DATA_URL);
  if (!res.ok) throw new Error(`Cannot load data: HTTP ${res.status}`);
  cachedData = await res.json();
  cachedAt = Date.now();
  return cachedData;
}

// Gemini call with a time limit, so a slow model can be skipped.
async function callGemini(model, payload, key, timeoutMs) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(
      `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json", "x-goog-api-key": key },
        body: payload,
        signal: controller.signal,
      }
    );
    const data = await res.json().catch(() => ({}));
    return { status: res.status, ok: res.ok, data };
  } catch (err) {
    return { status: 504, ok: false, data: { error: { message: `${model} timed out` } } };
  } finally {
    clearTimeout(timer);
  }
}

function systemPrompt(context, store) {
  return `You are a BI assistant for a bookstore sales dashboard with five stores (STORE1-STORE5).
Answer ONLY using the data below. If the answer is not in the data, say so - never invent numbers.
The user is currently viewing ${store || "STORE1"}; if they don't name a store, answer about that one.
All money is in USD (EUR converted at 1 EUR = 1.2 USD). Dates use the format YYYY-MM-DD.
Users were reconciled: records are the same person when at most one of name/address/phone/email differs.
You may calculate from the data (sums, comparisons, averages, monthly totals, etc.).
Answer briefly and clearly in plain text (no markdown tables), in the language of the question.

DATA:
${context}`;
}

// ---------- main ----------
export default {
  async fetch(request, env) {
    const origin = request.headers.get("Origin") || "";

    if (request.method === "OPTIONS") return new Response(null, { headers: cors(origin) });
    if (request.method !== "POST") return json({ error: "Use POST" }, 405, origin);

    let body;
    try { body = await request.json(); } catch { return json({ error: "Invalid JSON" }, 400, origin); }

    const question = String(body.question || "").trim().slice(0, 1000);
    if (!question) return json({ error: "Empty question" }, 400, origin);
    const history = Array.isArray(body.history) ? body.history.slice(-6) : [];

    try {
      const data = await getData(env);
      const mentioned = [...question.toUpperCase().matchAll(/STORE\s*([1-9])/g)].map((m) => "STORE" + m[1]);
      const detailStores = mentioned.length ? mentioned : [body.store || "STORE1"];
      const context = buildContext(data, detailStores);
      const contents = [
        ...history.map((m) => ({
          role: m.role === "user" ? "user" : "model",
          parts: [{ text: String(m.text).slice(0, 2000) }],
        })),
        { role: "user", parts: [{ text: question }] },
      ];
      const request = {
        systemInstruction: { parts: [{ text: systemPrompt(context, body.store) }] },
        contents,
        generationConfig: {
          temperature: 0.2,
          maxOutputTokens: 2048,                   // thinking tokens count here too
          thinkingConfig: { thinkingLevel: "low" }, // less thinking = faster answers
        },
      };
      const payload = JSON.stringify(request);
      delete request.generationConfig.thinkingConfig;
      const payloadNoThinking = JSON.stringify(request);  // for models that reject thinkingLevel

      // Try the main model first, then fall back to others if Gemini is busy.
      const models = [env.MODEL || "gemini-3.8-flash", ...FALLBACK_MODELS]
        .filter((m, i, a) => a.indexOf(m) === i);
      let lastError = "Unknown error";

      const started = Date.now();
      for (const model of models) {
        const left = 80000 - (Date.now() - started);      // stay under Cloudflare's 100 s limit
        if (left < 5000) break;
        let res = await callGemini(model, payload, env.GEMINI_API_KEY, Math.min(30000, left));
        if (res.status === 400 && /thinking/i.test(res.data.error?.message || "")) {
          res = await callGemini(model, payloadNoThinking, env.GEMINI_API_KEY, Math.min(30000, left));
        }

        if (res.ok) {
          const answer = (res.data.candidates?.[0]?.content?.parts || [])
            .filter((p) => !p.thought)
            .map((p) => p.text || "").join("").trim();
          if (answer) return json({ answer, model }, 200, origin);
          lastError = `${model} returned an empty answer`;
          continue;
        }

        lastError = res.data.error?.message || `Gemini HTTP ${res.status}`;
        // 400 / 401 / 403 = real errors (e.g. bad key) -> stop; busy, slow or missing model -> try the next one
        if ([400, 401, 403].includes(res.status)) break;
      }
      return json({ error: lastError }, 502, origin);
    } catch (err) {
      return json({ error: String(err.message || err) }, 500, origin);
    }
  },
};
