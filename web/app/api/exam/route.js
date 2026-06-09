import * as cheerio from "cheerio";

// --- Config ---
const BASE = "https://makauttest3.ucanapply.com";
const GET_URL = `${BASE}/onlineexam/public/`;
const POST_URL = `${BASE}/onlineexam/public/livewire/message/login-page`;
const UA =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36";

const GEMINI_KEY = process.env.GEMINI_API_KEY || "";
const GROQ_KEY = process.env.GROQ_API_KEY || "";
const CEREBRAS_KEY = process.env.CEREBRAS_API_KEY || "";

function deepMerge(target, source) {
  for (const key of Object.keys(source)) {
    if (source[key] instanceof Object && key in target && target[key] instanceof Object) {
      deepMerge(target[key], source[key]);
    } else {
      target[key] = source[key];
    }
  }
  return target;
}

export const maxDuration = 300;

// ─── Cookie Jar helper ───
class CookieJar {
  constructor() { this.cookies = {}; }
  update(res) {
    const raw = res.headers.getSetCookie?.() || [];
    for (const h of raw) {
      const [pair] = h.split(";");
      const [k, ...rest] = pair.split("=");
      this.cookies[k.trim()] = rest.join("=").trim();
    }
  }
  header() {
    return Object.entries(this.cookies).map(([k, v]) => `${k}=${v}`).join("; ");
  }
  get(name) { return this.cookies[name] || ""; }
}

// ─── fetch helper ───
async function f(url, jar, opts = {}) {
  const headers = {
    "User-Agent": UA,
    Accept: "text/html, application/xhtml+xml, application/xml",
    "Accept-Language": "en-US,en;q=0.9",
    Cookie: jar.header(),
    ...opts.headers,
  };
  const res = await fetch(url, {
    ...opts,
    headers,
    // @ts-ignore — Node undici supports this
    dispatcher: undefined,
  });
  jar.update(res);
  return res;
}

// ─── AI Functions ───
async function askGemini(prompt) {
  try {
    const r = await fetch(
      `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-lite:generateContent?key=${GEMINI_KEY}`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          contents: [{ parts: [{ text: prompt }] }],
          generationConfig: { temperature: 0.1, maxOutputTokens: 500 },
        }),
      }
    );
    const j = await r.json();
    return j?.candidates?.[0]?.content?.parts?.[0]?.text?.trim() || null;
  } catch { return null; }
}

async function askGroq(prompt) {
  try {
    const r = await fetch("https://api.groq.com/openai/v1/chat/completions", {
      method: "POST",
      headers: { Authorization: `Bearer ${GROQ_KEY}`, "Content-Type": "application/json" },
      body: JSON.stringify({
        model: "llama-3.3-70b-versatile",
        messages: [{ role: "user", content: prompt }],
        temperature: 0.1, max_tokens: 500,
      }),
    });
    const j = await r.json();
    return j?.choices?.[0]?.message?.content?.trim() || null;
  } catch { return null; }
}

async function askCerebras(prompt) {
  try {
    const r = await fetch("https://api.cerebras.ai/v1/chat/completions", {
      method: "POST",
      headers: { Authorization: `Bearer ${CEREBRAS_KEY}`, "Content-Type": "application/json" },
      body: JSON.stringify({
        model: "gpt-oss-120b",
        messages: [{ role: "user", content: prompt }],
        temperature: 0.1, max_tokens: 500,
      }),
    });
    const j = await r.json();
    return j?.choices?.[0]?.message?.content?.trim() || null;
  } catch { return null; }
}

function buildBatchPrompt(questions) {
  let lines = [
    "You are an expert academic exam solver with deep knowledge across all university subjects.",
    "Below are ALL the questions from an exam. Answer every single one.\n",
  ];
  for (const q of questions) {
    const opts = q.options.map((o, i) => `    ${i + 1}) ${o}`).join("\n");
    lines.push(`Q${q.number}:`, q.text, "  Options:", opts, "");
  }
  lines.push(
    "INSTRUCTIONS:",
    "- Answer ALL questions above.",
    "- For each question, respond with EXACTLY this format:  Q<number>: <option_number>",
    "- Example: Q1: 2",
    "- ONLY output the answers. No explanations.",
    "- Never skip a question.\n",
    "ANSWERS:"
  );
  return lines.join("\n");
}

function parseBatchResponse(text, total) {
  const answers = {};
  if (!text) return answers;
  for (const line of text.split("\n")) {
    const m = line.trim().match(/Q?(\d+)\s*[:.)\-]\s*(\d+)/i);
    if (m) {
      const qn = parseInt(m[1]), an = parseInt(m[2]);
      if (qn >= 1 && qn <= total && an >= 1 && an <= 10) answers[qn] = an;
    }
  }
  return answers;
}

// ─── Extract question data from HTML ───
function extractQuestion(html, pageNum) {
  const $ = cheerio.load(html);
  return {
    number: pageNum,
    q_id: $('input[name="q_id"]').val() || "",
    option_order: $('input[name="option_order"]').val() || "",
    q_type: $('input[name="q_type"]').val() || "mcq",
    display_pos: $('input[name="display_pos"]').val() || String(pageNum),
    screen: $('input[name="screen"]').val() || String(pageNum),
    text: $("div.question").text().trim() || `Question ${pageNum}`,
    options: $("label.checkcontainer").map((_, el) => $(el).find("div").first().text().trim()).get(),
    option_values: $("label.checkcontainer").map((_, el) => $(el).find("input").val() || "").get(),
  };
}

// ═══════════════════════════════════════════
// MAIN SSE HANDLER
// ═══════════════════════════════════════════
export async function POST(req) {
  const { username, password, referral } = await req.json();
  const encoder = new TextEncoder();

  const stream = new ReadableStream({
    async start(controller) {
      const send = (d) => controller.enqueue(encoder.encode(`data: ${JSON.stringify(d)}\n\n`));

      try {
        if (referral !== "IHerbyFuckYou") {
          send({ phase: "error", message: "Access Denied: Invalid referral code." });
          controller.close();
          return;
        }

        const jar = new CookieJar();

        // ── Step 1: GET login page ──
        const pageRes = await f(GET_URL, jar);
        const pageHtml = await pageRes.text();
        const $page = cheerio.load(pageHtml);

        const csrfToken = $page('meta[name="csrf-token"]').attr("content");
        const loginDiv = $page("div.login-form1");
        if (!csrfToken || !loginDiv.length) {
          send({ phase: "error", message: "Portal structure changed — cannot find login form." });
          controller.close(); return;
        }

        const lwData = JSON.parse(loginDiv.attr("wire:initial-data"));

        // ── Step 2: POST login ──
        send({ phase: "login", step: "Authenticating with MAKAUT..." });
        const loginPayload = {
          fingerprint: lwData.fingerprint,
          serverMemo: lwData.serverMemo,
          updates: [
            { type: "syncInput", payload: { name: "password", value: password } },
            { type: "syncInput", payload: { name: "username", value: username } },
            { type: "callMethod", payload: { method: "submit", params: [] } },
          ],
        };

        let loginRes = await f(POST_URL, jar, {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-Livewire": "true", "X-CSRF-TOKEN": csrfToken, Origin: BASE, Referer: GET_URL },
          body: JSON.stringify(loginPayload),
        });
        let loginJson = await loginRes.json();

        // Handle already-logged-in
        if (loginJson?.serverMemo?.data?.alreadySession === "Y") {
          send({ phase: "login", step: "Destroying previous session..." });
          const newMemo = loginJson.serverMemo;
          loginPayload.serverMemo.htmlHash = newMemo.htmlHash || loginPayload.serverMemo.htmlHash;
          loginPayload.serverMemo.checksum = newMemo.checksum || loginPayload.serverMemo.checksum;
          if (newMemo.data) Object.assign(loginPayload.serverMemo.data, newMemo.data);
          loginPayload.updates = [
            { type: "callMethod", payload: { method: "$set", params: ["destroy", "Y"] } },
            { type: "callMethod", payload: { method: "submit", params: [] } },
          ];
          loginRes = await f(POST_URL, jar, {
            method: "POST",
            headers: { "Content-Type": "application/json", "X-Livewire": "true", "X-CSRF-TOKEN": csrfToken, Origin: BASE, Referer: GET_URL },
            body: JSON.stringify(loginPayload),
          });
          loginJson = await loginRes.json();
        }

        const redirect = loginJson?.effects?.redirect;
        if (!redirect) {
          const errHtml = loginJson?.effects?.html || "";
          const $err = cheerio.load(errHtml);
          const errMsg = $err("div.alert-danger").text().replace("×", "").trim();
          send({ phase: "error", message: errMsg || "Login failed — check credentials." });
          controller.close(); return;
        }

        // ── Step 3: Dashboard ──
        const dashRes = await f(redirect, jar);
        const dashHtml = await dashRes.text();
        const $dash = cheerio.load(dashHtml);
        const welcome = $dash("div.alert-success").text().replace("×", "").trim() || "Student";
        send({ phase: "login", step: `Welcome, ${welcome}` });

        // ── Step 4: Active papers ──
        send({ phase: "login", step: "Scanning for active exams..." });
        const xsrf = decodeURIComponent(jar.get("XSRF-TOKEN"));
        const papersRes = await f(`${BASE}/onlineexam/public/student/getActivePapper`, jar, {
          headers: { "X-Requested-With": "XMLHttpRequest", "X-XSRF-TOKEN": xsrf },
        });
        const papersJson = await papersRes.json();
        const $papers = cheerio.load(papersJson.html || "");

        if ($papers.text().includes("No Paper Found")) {
          send({ phase: "error", message: "No active exam found right now." });
          controller.close(); return;
        }

        const paperLink = $papers("a.list-group-item").first();
        const paperUrl = paperLink.attr("href");
        const paperTitle = paperLink.find("h5").text().trim() || "Exam";
        send({ phase: "papers", step: `Exam Found: ${paperTitle}`, title: paperTitle });

        // ── Step 5: Exam instructions + start ──
        const instrRes = await f(paperUrl, jar);
        const instrText = await instrRes.text();

        const paperID = instrText.match(/paperID:\s*(\d+)/)?.[1];
        const paper_type = instrText.match(/paper_type:\s*(\d+)/)?.[1];
        const start_date = instrText.match(/start_date:\s*(\d+)/)?.[1];
        const crypt_name = instrText.match(/crypt_name:\s*["']([^"']+)["']/)?.[1];

        if (!paperID) {
          send({ phase: "error", message: "Cannot extract exam start payload." });
          controller.close(); return;
        }

        const xsrf2 = decodeURIComponent(jar.get("XSRF-TOKEN"));
        const startRes = await f(`${BASE}/onlineexam/public/student/check-exam-started-invigilator`, jar, {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest", "X-XSRF-TOKEN": xsrf2 },
          body: JSON.stringify({ paperID: +paperID, paper_type: +paper_type, start_date: +start_date, crypt_name }),
        });
        const startJson = await startRes.json();

        if (!startJson.status) {
          send({ phase: "error", message: startJson.msg || "Exam start rejected by server." });
          controller.close(); return;
        }

        send({ phase: "exam", step: "Exam session started. Extracting questions..." });
        const examRes = await f(startJson.url, jar);
        const examHtml = await examRes.text();
        const $exam = cheerio.load(examHtml);
        const examCsrf = $exam('meta[name="csrf-token"]').attr("content") || csrfToken;

        // Find questionbutton component
        let qComp = null;
        $exam("[wire\\:initial-data]").each((_, el) => {
          try {
            const d = JSON.parse(cheerio.load(el).root().children().first().attr("wire:initial-data"));
            if (d?.fingerprint?.name === "questionbutton") qComp = d;
          } catch {}
        });

        if (!qComp) {
          send({ phase: "error", message: "Cannot find question component on exam page." });
          controller.close(); return;
        }

        const qUrl = `${BASE}/onlineexam/public/livewire/message/questionbutton`;
        const qHeaders = {
          Accept: "text/html, application/xhtml+xml",
          "Content-Type": "application/json",
          "X-Livewire": "true",
          "X-CSRF-TOKEN": examCsrf,
          Origin: BASE,
          Referer: startJson.url,
        };

        // ══════════════════════════════════════
        // PHASE 1: COLLECT ALL QUESTIONS
        // ══════════════════════════════════════
        const q1Res = await f(qUrl, jar, {
          method: "POST",
          headers: qHeaders,
          body: JSON.stringify({
            fingerprint: qComp.fingerprint,
            serverMemo: qComp.serverMemo,
            updates: [{ type: "callMethod", payload: { method: "loadQuestion", params: [] } }],
          }),
        });
        const q1Json = await q1Res.json();

        let memo = JSON.parse(JSON.stringify(qComp.serverMemo));
        const nm1 = q1Json.serverMemo || {};
        if (nm1) deepMerge(memo, nm1);

        const q1Html = q1Json?.effects?.html || "";
        const $q1 = cheerio.load(q1Html);

        let totalPages = 1;
        $q1("[wire\\:click]").each((_, el) => {
          const m = cheerio.load(el).root().text();
          const wc = cheerio.load(el).root().children().first().attr("wire:click") || "";
          const pm = wc.match(/setCurrentPages\((\d+)\)/);
          if (pm) totalPages = Math.max(totalPages, parseInt(pm[1]));
        });

        const allQuestions = [];
        send({ phase: "collect_start", total: totalPages });

        const q1Data = extractQuestion(q1Html, 1);
        allQuestions.push(q1Data);
        send({ phase: "collect", q: q1Data });

        let currentQData = q1Data;
        for (let p = 2; p <= totalPages; p++) {
          const markData = {
            screen: currentQData.screen,
            currentScreen: currentQData.screen,
            answer: "",
            option_order: currentQData.option_order,
            q_id: currentQData.q_id,
            display_pos: currentQData.display_pos,
            q_type: currentQData.q_type
          };
          const navRes = await f(qUrl, jar, {
            method: "POST",
            headers: qHeaders,
            body: JSON.stringify({
              fingerprint: qComp.fingerprint,
              serverMemo: memo,
              updates: [
                { type: "callMethod", payload: { method: "setCurrentPages", params: [p] } },
                { type: "callMethod", payload: { method: "recordMarks", params: [markData] } }
              ],
            }),
          });
          const navJson = await navRes.json();
          const nm = navJson.serverMemo || {};
          if (nm) deepMerge(memo, nm);

          const ph = navJson?.effects?.html || "";
          if (ph) {
            const qData = extractQuestion(ph, p);
            allQuestions.push(qData);
            send({ phase: "collect", q: qData });
            currentQData = qData;
          }
        }

        // ══════════════════════════════════════
        // PHASE 2: AI BATCH SOLVE
        // ══════════════════════════════════════
        send({ phase: "solve_start", total: allQuestions.length });

        const prompt = buildBatchPrompt(allQuestions);
        const [geminiRaw, groqRaw, cerebrasRaw] = await Promise.all([
          askGemini(prompt), askGroq(prompt), askCerebras(prompt),
        ]);

        const geminiAns = parseBatchResponse(geminiRaw, allQuestions.length);
        const groqAns = parseBatchResponse(groqRaw, allQuestions.length);
        const cerebrasAns = parseBatchResponse(cerebrasRaw, allQuestions.length);

        let consensus = 0, tiebreak = 0, fallback = 0;
        const results = [];

        for (const q of allQuestions) {
          const n = q.number, max = q.options.length;
          const g = geminiAns[n] && geminiAns[n] <= max ? geminiAns[n] : null;
          const r = groqAns[n] && groqAns[n] <= max ? groqAns[n] : null;
          const c = cerebrasAns[n] && cerebrasAns[n] <= max ? cerebrasAns[n] : null;
          const votes = [g, r, c].filter(Boolean);

          let final, method;
          if (!votes.length) {
            final = Math.floor(Math.random() * max) + 1; method = "RANDOM"; fallback++;
          } else {
            const freq = {};
            votes.forEach((v) => (freq[v] = (freq[v] || 0) + 1));
            const sorted = Object.entries(freq).sort((a, b) => b[1] - a[1]);
            if (sorted[0][1] >= 2) {
              final = +sorted[0][0]; method = `CONSENSUS (${sorted[0][1]}/3)`; consensus++;
            } else if (g) {
              final = g; method = "TIEBREAK (Gemini)"; tiebreak++;
            } else {
              final = +sorted[0][0]; method = "TIEBREAK"; tiebreak++;
            }
          }

          q.ai_answer_index = final - 1;
          q.ai_answer_value = q.option_values[final - 1];
          const finalOptText = q.options[final - 1] || "?";

          const resData = {
            number: n,
            text: q.text.substring(0, 120),
            gemini: g, groq: r, cerebras: c,
            final, method,
            optionText: finalOptText,
          };
          results.push(resData);
          send({ phase: "solve_progress", result: resData });
        }

        send({
          phase: "solved",
          results,
          stats: { total: allQuestions.length, consensus, tiebreak, fallback },
        });

        // ══════════════════════════════════════
        // PHASE 3: SUBMIT ALL ANSWERS
        // ══════════════════════════════════════
        send({ phase: "submit_start", total: allQuestions.length });

        // Go back to Q1
        const lastQ = allQuestions[allQuestions.length - 1];
        const jumpMarkData = {
          screen: lastQ.screen, currentScreen: lastQ.screen, answer: "",
          option_order: lastQ.option_order, q_id: lastQ.q_id,
          display_pos: lastQ.display_pos, q_type: lastQ.q_type
        };
        const backRes = await f(qUrl, jar, {
          method: "POST",
          headers: qHeaders,
          body: JSON.stringify({
            fingerprint: qComp.fingerprint,
            serverMemo: memo,
            updates: [
              { type: "callMethod", payload: { method: "setCurrentPages", params: [1] } },
              { type: "callMethod", payload: { method: "recordMarks", params: [jumpMarkData] } }
            ],
          }),
        });
        const backJson = await backRes.json();
        const nmb = backJson.serverMemo || {};
        if (nmb) deepMerge(memo, nmb);

        for (let i = 0; i < allQuestions.length; i++) {
          const q = allQuestions[i];
          const nextPage = q.number < totalPages ? q.number + 1 : q.number;
          const markData = {
            screen: q.screen, currentScreen: q.screen, answer: q.ai_answer_value,
            option_order: q.option_order, q_id: q.q_id, display_pos: q.display_pos, q_type: q.q_type,
          };

          const sRes = await f(qUrl, jar, {
            method: "POST",
            headers: qHeaders,
            body: JSON.stringify({
              fingerprint: qComp.fingerprint,
              serverMemo: memo,
              updates: [
                { type: "callMethod", payload: { method: "setCurrentPages", params: [nextPage] } },
                { type: "callMethod", payload: { method: "recordMarks", params: [markData] } }
              ],
            }),
          });
          const sJson = await sRes.json();
          const nms = sJson.serverMemo || {};
          if (nms) deepMerge(memo, nms);

          send({ phase: "submit", current: i + 1, qNum: q.number, answer: q.ai_answer_value, optIdx: q.ai_answer_index + 1 });
        }

        send({ phase: "done", message: `Chill karo completed! ${allQuestions.length} answers successfully recorded.` });
      } catch (err) {
        send({ phase: "error", message: err.message || "Unexpected error." });
      }
      controller.close();
    },
  });

  return new Response(stream, {
    headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache", Connection: "keep-alive" },
  });
}
