"use client";
import { useState, useRef, useEffect } from "react";

const PHASES = { LOGIN: 0, RUNNING: 1, RESULTS: 2 };

export default function Home() {
  const [phase, setPhase] = useState(PHASES.LOGIN);
  const [roll, setRoll] = useState("");
  const [pass, setPass] = useState("");
  const [referral, setReferral] = useState("");
  const [logs, setLogs] = useState([]);
  const [progress, setProgress] = useState({ text: "", pct: 0 });
  const [results, setResults] = useState(null);
  const [stats, setStats] = useState(null);
  const [error, setError] = useState("");
  const [dashboard, setDashboard] = useState(null);
  const logsEnd = useRef(null);

  useEffect(() => { logsEnd.current?.scrollIntoView({ behavior: "smooth" }); }, [logs]);

  const addLog = (msg, type = "info") => setLogs((p) => [...p, { msg, type, ts: Date.now() }]);

  async function startExam(e) {
    e.preventDefault();
    if (!roll.trim() || !pass.trim()) return;
    setPhase(PHASES.RUNNING);
    setLogs([]);
    setError("");
    setResults(null);
    setStats(null);
    setDashboard(null);
    addLog("Connecting to MAKAUT portal...", "system");

    try {
      const res = await fetch("/api/exam", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: roll.trim(), password: pass.trim(), referral: referral.trim() }),
      });

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const d = JSON.parse(line.slice(6));
            handleEvent(d);
          } catch {}
        }
      }
    } catch (err) {
      setError(err.message || "Network error");
      addLog(`Error: ${err.message}`, "error");
    }
  }

  function handleEvent(d) {
    switch (d.phase) {
      case "login":
        if (d.step) addLog(d.step, "system");
        setProgress({ text: d.step || "Authenticating...", pct: 5 });
        break;
      case "dashboard":
        setDashboard(d);
        addLog(`Access Granted: ${d.welcome}`, "success");
        setProgress({ text: "Dashboard loaded", pct: 10 });
        break;
      case "papers":
        addLog(d.step, d.title ? "success" : "system");
        setProgress({ text: "Scanning exams...", pct: 15 });
        break;
      case "exam":
        addLog(d.step, "info");
        setProgress({ text: "Initializing exam...", pct: 20 });
        break;
      case "collect_start":
        addLog(`Total questions found: ${d.total}. Commencing extraction.`, "system");
        setProgress({ text: `Extracting 0/${d.total}`, pct: 20 });
        break;
      case "collect":
        addLog(`[Q${d.q.number}] ${d.q.text}`, "info");
        d.q.options.forEach((opt, idx) => addLog(`  ↳ Opt ${idx + 1}: ${opt}`, "system"));
        setProgress({ text: `Extracting ${d.q.number}`, pct: 20 + (d.q.number / 50) * 30 }); // Estimate
        break;
      case "solve_start":
        addLog(`--- INITIATING AI ENSEMBLE BATCH SOLVE ---`, "success");
        addLog(`Routing ${d.total} questions to Gemini, Groq & Cerebras...`, "system");
        setProgress({ text: "AI models analyzing...", pct: 55 });
        break;
      case "solve_progress":
        const r = d.result;
        setLogs((p) => [...p, { type: "ai_solve", data: r, ts: Date.now() }]);
        break;
      case "solved":
        setResults(d.results);
        setStats(d.stats);
        addLog(`--- AI ANALYSIS COMPLETE ---`, "success");
        setProgress({ text: "AI analysis complete", pct: 75 });
        break;
      case "submit_start":
        addLog(`Navigating to start of exam to record marks...`, "system");
        setProgress({ text: `Submitting answers...`, pct: 75 });
        break;
      case "submit":
        addLog(`[Q${d.qNum}] Successfully submitted Opt ${d.optIdx} ✓`, "success");
        setProgress({ text: `Submitting: ${d.current}`, pct: 75 + (d.current / 50) * 25 });
        break;
      case "done":
        addLog(d.message, "success");
        setProgress({ text: "Complete!", pct: 100 });
        setPhase(PHASES.RESULTS);
        break;
      case "error":
        setError(d.message);
        addLog(`Error: ${d.message}`, "error");
        break;
    }
  }

  return (
    <div className="app">
      {/* Animated grid background */}
      <div className="grid-bg" />
      <div className="glow-orb orb1" />
      <div className="glow-orb orb2" />
      <div className="scanline" />

      <header className="header">
        <div className="logo">
          <span className="logo-icon">⚡</span>
          <span className="logo-text">CHILL<span className="accent">KARO</span></span>
        </div>
        <div className="badge">AI ENSEMBLE v2.0</div>
      </header>

      <main className="main">
        {phase === PHASES.LOGIN && (
          <form className="card login-card" onSubmit={startExam}>
            {/* Sci-Fi HUD Elements */}
            <div className="hud-corner top-left"></div>
            <div className="hud-corner top-right"></div>
            <div className="hud-corner bottom-left"></div>
            <div className="hud-corner bottom-right"></div>
            <div className="scanner-line"></div>
            <div className="card-glow" />

            <div className="title-wrapper">
              <h1 className="card-title neon-title">
                <span className="title-word">CHILL</span>
                <span className="title-word accent-gradient">KARO</span>
              </h1>
              <div className="title-reflection">CHILL KARO</div>
            </div>
            
            <p className="card-sub type-writer">sys.init() // 3-AI Ensemble active</p>

            <div className="input-group">
              <label className="input-label">ROLL NUMBER</label>
              <div className="input-wrap">
                <span className="input-icon">◆</span>
                <input
                  id="roll-input"
                  type="text"
                  className="input"
                  placeholder="Enter your roll number"
                  value={roll}
                  onChange={(e) => setRoll(e.target.value)}
                  autoComplete="off"
                />
              </div>
            </div>

            <div className="input-group">
              <label className="input-label">PASSWORD</label>
              <div className="input-wrap">
                <span className="input-icon">◆</span>
                <input
                  id="pass-input"
                  type="password"
                  className="input"
                  placeholder="Enter your password"
                  value={pass}
                  onChange={(e) => setPass(e.target.value)}
                />
              </div>
            </div>

            <div className="input-group">
              <label className="input-label">REFERRAL CODE</label>
              <div className="input-wrap">
                <span className="input-icon">◆</span>
                <input
                  id="referral-input"
                  type="password"
                  className="input"
                  placeholder="Enter system access code"
                  value={referral}
                  onChange={(e) => setReferral(e.target.value)}
                />
              </div>
            </div>

            <button id="start-btn" type="submit" className="btn-primary" disabled={!roll || !pass || !referral}>
              <span className="btn-text">INITIALIZE EXAM</span>
              <span className="btn-arrow">→</span>
            </button>

            <div className="features">
              <div className="feat"><span className="feat-dot g" />Gemini 2.5 Flash</div>
              <div className="feat"><span className="feat-dot b" />Groq Llama 70B</div>
              <div className="feat"><span className="feat-dot p" />Cerebras Llama 70B</div>
            </div>
          </form>
        )}

        {(phase === PHASES.RUNNING || phase === PHASES.RESULTS) && (
          <div className="dashboard">
            {/* Progress bar */}
            <div className="progress-section">
              <div className="progress-header">
                <span className="progress-label">{progress.text}</span>
                <span className="progress-pct">{Math.round(progress.pct)}%</span>
              </div>
              <div className="progress-track">
                <div className="progress-fill" style={{ width: `${progress.pct}%` }} />
                <div className="progress-glow" style={{ left: `${progress.pct}%` }} />
              </div>
            </div>

            {error && <div className="error-banner">{error}</div>}

            {/* Results table */}
            {results && (
              <div className="card results-card">
                <h2 className="section-title">AI ANSWER MATRIX</h2>
                {stats && (
                  <div className="stats-row">
                    <div className="stat">
                      <span className="stat-val accent">{stats.consensus}</span>
                      <span className="stat-label">Consensus</span>
                    </div>
                    <div className="stat">
                      <span className="stat-val warn">{stats.tiebreak}</span>
                      <span className="stat-label">Tiebreak</span>
                    </div>
                    <div className="stat">
                      <span className="stat-val err">{stats.fallback}</span>
                      <span className="stat-label">Fallback</span>
                    </div>
                    <div className="stat">
                      <span className="stat-val">{Math.round(
                        (stats.consensus * 90 + stats.tiebreak * 70 + stats.fallback * 25) / Math.max(stats.total, 1)
                      )}%</span>
                      <span className="stat-label">Est. Accuracy</span>
                    </div>
                  </div>
                )}
                <div className="table-wrap">
                  <table className="results-table">
                    <thead>
                      <tr>
                        <th>Q#</th><th>Gemini</th><th>Groq</th><th>Cerebras</th><th>Final</th><th>Method</th>
                      </tr>
                    </thead>
                    <tbody>
                      {results.map((r, i) => (
                        <tr key={i} className={`row-anim`} style={{ animationDelay: `${i * 40}ms` }}>
                          <td className="q-num">Q{r.number}</td>
                          <td className={r.gemini === r.final ? "match" : ""}>{r.gemini ? `Opt ${r.gemini}` : "—"}</td>
                          <td className={r.groq === r.final ? "match" : ""}>{r.groq ? `Opt ${r.groq}` : "—"}</td>
                          <td className={r.cerebras === r.final ? "match" : ""}>{r.cerebras ? `Opt ${r.cerebras}` : "—"}</td>
                          <td className="final-answer">Opt {r.final}</td>
                          <td className={`method ${r.method.includes("CONSENSUS") ? "consensus" : r.method.includes("TIE") ? "tie" : "random"}`}>
                            {r.method}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* Live log */}
            <div className="card log-card">
              <h2 className="section-title">LIVE FEED</h2>
              <div className="log-scroll">
                {logs.map((l, i) => {
                  if (l.type === "ai_solve") {
                    const r = l.data;
                    return (
                      <div key={i} className="log-line" style={{ display: 'block', background: 'rgba(0, 0, 0, 0.4)', border: '1px solid rgba(0, 240, 255, 0.2)', borderRadius: '6px', padding: '12px', margin: '8px 0', borderLeft: '3px solid #00f0ff' }}>
                        <div style={{ color: '#00f0ff', fontWeight: 'bold', marginBottom: '8px', fontSize: '0.95em' }}>
                          Q{r.number}: {r.text}
                        </div>
                        <div style={{ paddingLeft: '12px', marginBottom: '10px', color: '#a0aab5', fontSize: '0.85em', display: 'flex', flexDirection: 'column', gap: '4px' }}>
                          {r.options && r.options.map((opt, idx) => (
                            <div key={idx} style={{ 
                              color: (idx + 1) === r.final ? '#00ffaa' : 'inherit', 
                              fontWeight: (idx + 1) === r.final ? 'bold' : 'normal',
                              display: 'flex', gap: '8px'
                            }}>
                              <span style={{ opacity: 0.6 }}>{idx + 1}.</span> 
                              <span>{opt} {(idx + 1) === r.final && '✓'}</span>
                            </div>
                          ))}
                        </div>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', fontSize: '0.8em', borderTop: '1px solid rgba(255,255,255,0.05)', paddingTop: '8px', marginBottom: '6px' }}>
                          <div><span style={{ color: '#777' }}>Gemini:</span> <span style={{ color: r.gemini ? '#00f0ff' : '#ff4444' }}>{r.gemini ? `Opt ${r.gemini}` : "FAIL"}</span></div>
                          <div><span style={{ color: '#777' }}>Groq:</span> <span style={{ color: r.groq ? '#00f0ff' : '#ff4444' }}>{r.groq ? `Opt ${r.groq}` : "FAIL"}</span></div>
                          <div><span style={{ color: '#777' }}>Cerebras:</span> <span style={{ color: r.cerebras ? '#00f0ff' : '#ff4444' }}>{r.cerebras ? `Opt ${r.cerebras}` : "FAIL"}</span></div>
                        </div>
                        <div style={{ color: '#ffb000', fontSize: '0.85em', fontWeight: 'bold' }}>
                          ↳ FINAL: Option {r.final} <span style={{ opacity: 0.7, fontWeight: 'normal', fontSize: '0.9em' }}>({r.method})</span>
                        </div>
                      </div>
                    );
                  }
                  return (
                    <div key={i} className={`log-line log-${l.type}`}>
                      <span className="log-time">{new Date(l.ts).toLocaleTimeString()}</span>
                      <span className="log-msg">{l.msg}</span>
                    </div>
                  );
                })}
                <div ref={logsEnd} />
              </div>
            </div>

            {phase === PHASES.RESULTS && (
              <button className="btn-primary btn-reset" onClick={() => { setPhase(PHASES.LOGIN); setRoll(""); setPass(""); setReferral(""); }}>
                <span className="btn-text">NEW SESSION</span>
                <span className="btn-arrow">↻</span>
              </button>
            )}
          </div>
        )}
      </main>

      <footer className="footer">
        <span>Powered by 3-AI Ensemble</span>
        <span className="footer-dot">•</span>
        <span>Gemini + Groq + Cerebras</span>
      </footer>
    </div>
  );
}
