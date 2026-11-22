import { useEffect, useRef, useState } from "react";
import { TOKEN_KEY } from "../../api.js";
import { HeroPreview, Showcase, SkillPreview, SuitePreview,
  RegressionPreview, ReportPreview } from "./previews.jsx";
import "./landing.css";

/* Public landing — shown before sign-in. Light premium dev-tool design,
   copy targets AI automation agencies. Every preview is labelled sample
   data; every CTA lands on the embedded sign-in card that enters the app. */

const GITHUB = "https://github.com/kien2803/SkillLab";

function Reveal({ children, className = "", ...rest }) {
  const ref = useRef(null);
  const [inView, setInView] = useState(false);
  useEffect(() => {
    const io = new IntersectionObserver((es) => es.forEach((e) => {
      if (e.isIntersecting) { setInView(true); io.disconnect(); }
    }), { threshold: .12 });
    if (ref.current) io.observe(ref.current);
    return () => io.disconnect();
  }, []);
  return <div ref={ref} className={`lp-rev ${inView ? "in" : ""} ${className}`}
    {...rest}>{children}</div>;
}

const FAQ = [
  ["What is SkillLab?",
   "An open-source benchmarking and QA workbench for AI Agent Skills. It runs controlled experiments — the same tasks with and without a skill — evaluates every rollout against a rubric, detects regressions between versions, and produces evidence-based quality reports."],
  ["Which AI Agent Skills can I test?",
   "Any skill in the standard SKILL.md format. Import skills from a git URL, or let SkillLab scan the usual agent skill directories (~/.agents/skills, ~/.claude/skills, ~/.config/devin/skills). Variants are immutable, so every version you test stays reproducible."],
  ["How does benchmarking work?",
   "You pick a task suite and a rubric; SkillLab runs a control arm (no skill) and a treatment arm (your skill, available or injected) under a fixed model configuration, then evaluates each rollout. The result is a score matrix with per-task deltas — improvement is always measured against the no-skill baseline."],
  ["Can I compare different skill versions?",
   "Yes — regression suites run a baseline variant against a candidate across the same suite and report a verdict (clean, regressed or inconclusive) across six categories: critical, quality, activation, false-activation, efficiency and stability, with per-task evidence."],
  ["Can I export reports for clients?",
   "Yes. Quality reports pin evidence to the exact content hash that was tested, show the benchmark and regression results and the release checklist, and export as Markdown you can hand to a client."],
  ["Which models and runtimes are supported?",
   "Any LiteLLM provider string — anthropic/, openai/, gemini/, ollama/ — plus a mock model for deterministic offline development and cmd: drivers for custom agent frameworks. Real runs need the provider's API key in the server environment; mock runs are always labelled simulated."],
];

export default function Landing() {
  const enterRef = useRef(null);
  const [tk, setTk] = useState("");
  const [err, setErr] = useState("");
  const [menu, setMenu] = useState(false);
  const signIn = () => {
    setMenu(false);
    enterRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
  };
  const tryToken = async () => {
    const v = tk.trim();
    if (!v) return;
    const r = await fetch("/api/v1/status",
      { headers: { Authorization: `Bearer ${v}` } });
    if (r.ok) {
      localStorage.setItem(TOKEN_KEY, v);
      window.dispatchEvent(new Event("storage"));
    } else {
      setErr(`invalid token (${r.status})`);
    }
  };

  return <div className="lp">
    {/* ---------- nav ---------- */}
    <header className="lp-nav">
      <div className="lp-nav-in">
        <a className="lp-logo" href="#top" aria-label="SkillLab home">
          <i>λ</i>SkillLab</a>
        <nav className="lp-links" aria-label="Sections">
          <a href="#product">Product</a>
          <a href="#how">How It Works</a>
          <a href="#features">Features</a>
          <a href="#faq">FAQ</a>
        </nav>
        <div className="lp-nav-cta">
          <button className="signin" onClick={signIn}>Sign In</button>
          <button className="lp-btn sm" onClick={signIn}>Get Started</button>
          <button className="lp-burger" aria-label="Menu"
            aria-expanded={menu} onClick={() => setMenu((m) => !m)}>☰</button>
        </div>
      </div>
      <nav className={`lp-mobilemenu ${menu ? "open" : ""}`}>
        <a href="#product" onClick={() => setMenu(false)}>Product</a>
        <a href="#how" onClick={() => setMenu(false)}>How It Works</a>
        <a href="#features" onClick={() => setMenu(false)}>Features</a>
        <a href="#faq" onClick={() => setMenu(false)}>FAQ</a>
        <button className="mlink" onClick={signIn}>Sign In</button>
      </nav>
    </header>

    {/* ---------- hero ---------- */}
    <section className="lp-hero" id="top">
      <div className="lp-hero-grid">
        <div>
          <p className="lp-eyebrow">Skill benchmarking &amp; QA · for AI automation agencies</p>
          <h1>Know if your AI skills <em>actually work.</em></h1>
          <p className="lede">Benchmark, compare, and improve AI Agent Skills
            with reproducible tests. Find out what works, what fails, and
            what changes before deployment.</p>
          <div className="lp-hero-ctas">
            <button className="lp-btn" onClick={signIn}>Start Benchmarking</button>
            <a className="lp-btn ghost" href="#how">See How It Works</a>
          </div>
          <p className="lp-hero-note">open source · yaml + markdown lab · no database</p>
        </div>
        <HeroPreview />
      </div>
    </section>

    {/* ---------- problem ---------- */}
    <section className="lp-problem" id="product">
      <div className="wrap">
        <Reveal>
          <p className="lp-eyebrow">The problem</p>
          <h2 className="lp-h2">Stop guessing. Start benchmarking.</h2>
        </Reveal>
        <div className="lp-cards3">
          <Reveal><div className="lp-card">
            <div className="num">01</div>
            <h3>Unproven performance</h3>
            <p>You can't assume a skill improves an agent just because it
              looks well written. Only a controlled comparison tells.</p>
          </div></Reveal>
          <Reveal><div className="lp-card">
            <div className="num">02</div>
            <h3>Hidden regressions</h3>
            <p>A skill update can improve one task while quietly breaking
              another. Without a suite, you find out from your client.</p>
          </div></Reveal>
          <Reveal><div className="lp-card">
            <div className="num">03</div>
            <h3>No reliable evidence</h3>
            <p>Without reproducible evaluation, "it feels better" is the best
              answer you can give a client. Reports need proof, not vibes.</p>
          </div></Reveal>
        </div>
      </div>
    </section>

    {/* ---------- how it works ---------- */}
    <section id="how">
      <div className="wrap">
        <Reveal>
          <p className="lp-eyebrow">Workflow</p>
          <h2 className="lp-h2">From skill to measurable results.</h2>
        </Reveal>
        <div className="lp-steps">
          <Reveal><div className="lp-step">
            <div className="dot">01</div>
            <h3>Import</h3>
            <p>Bring your AI Agent Skills into SkillLab — from git or a
              scanned directory. Versions stay immutable.</p>
          </div></Reveal>
          <Reveal><div className="lp-step">
            <div className="dot">02</div>
            <h3>Benchmark</h3>
            <p>Test them against consistent task suites and a no-skill
              baseline under a fixed model configuration.</p>
          </div></Reveal>
          <Reveal><div className="lp-step">
            <div className="dot">03</div>
            <h3>Improve</h3>
            <p>Inspect failures, detect regressions, and validate each new
              version before it reaches a client.</p>
          </div></Reveal>
        </div>
      </div>
    </section>

    {/* ---------- features ---------- */}
    <section className="lp-feats" id="features">
      <div className="wrap">
        <Reveal>
          <p className="lp-eyebrow">Core modules</p>
          <h2 className="lp-h2">Everything you need to validate a skill.</h2>
        </Reveal>
        <div className="lp-featgrid">
          <Reveal><div className="lp-feat">
            <div className="head">
              <h3>Skill Management</h3>
              <p>Import, organize, edit, and version your skills — with
                revision history and safe in-browser editing.</p>
            </div>
            <div className="shot"><SkillPreview /></div>
          </div></Reveal>
          <Reveal><div className="lp-feat">
            <div className="head">
              <h3>Test Suites</h3>
              <p>Build reusable test cases and evaluation criteria —
                trigger, performance, and negative tasks with rubrics.</p>
            </div>
            <div className="shot"><SuitePreview /></div>
          </div></Reveal>
          <Reveal><div className="lp-feat">
            <div className="head">
              <h3>Benchmark &amp; Regression</h3>
              <p>Compare baseline vs skill and detect performance
                regressions between versions — per task, with evidence.</p>
            </div>
            <div className="shot"><RegressionPreview /></div>
          </div></Reveal>
          <Reveal><div className="lp-feat">
            <div className="head">
              <h3>Quality Reports</h3>
              <p>Generate evidence-based reports pinned to the exact
                content tested — exportable for your team and clients.</p>
            </div>
            <div className="shot"><ReportPreview /></div>
          </div></Reveal>
        </div>
      </div>
    </section>

    {/* ---------- showcase ---------- */}
    <section id="showcase">
      <div className="wrap">
        <Reveal>
          <div className="lp-show-head">
            <div>
              <p className="lp-eyebrow">Benchmark comparison</p>
              <h2 className="lp-h2">See what actually changed.</h2>
              <p className="lp-lede">Every run pinned to the exact skill
                content. Improved tasks, regressed tasks, and the evidence
                behind each verdict — inspect any individual test case.</p>
            </div>
          </div>
        </Reveal>
        <Reveal className="lp-dash"><Showcase /></Reveal>
      </div>
    </section>

    {/* ---------- faq ---------- */}
    <section className="lp-faq" id="faq">
      <div className="wrap">
        <Reveal style={{ textAlign: "center" }}>
          <p className="lp-eyebrow">Questions</p>
          <h2 className="lp-h2">Frequently asked</h2>
        </Reveal>
        <div className="lp-faq-list">
          {FAQ.map(([q, a]) =>
            <Reveal key={q}><details>
              <summary>{q}</summary><p>{a}</p>
            </details></Reveal>)}
        </div>
      </div>
    </section>

    {/* ---------- final cta ---------- */}
    <section className="lp-final">
      <Reveal><div className="lp-final-in">
        <h2>Stop guessing. Start proving.</h2>
        <p>Make your AI Agent Skills measurable, testable, and
          continuously improvable.</p>
        <button className="lp-btn" onClick={signIn}>Start Benchmarking</button>
        <div className="mono-note">free &amp; open source — {GITHUB.replace("https://", "")}</div>
      </div></Reveal>
    </section>

    {/* ---------- sign-in ---------- */}
    <section className="lp-enter" id="lp-enter" ref={enterRef}>
      <div className="card">
        <div className="wm2"><i>λ</i>SkillLab</div>
        <label htmlFor="lp-tok">API token</label>
        <input id="lp-tok" value={tk} placeholder="SKILLLAB_TOKEN"
          autoComplete="off"
          onChange={(e) => setTk(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && tryToken()} />
        {err && <div className="err">{err}</div>}
        <button className="lp-btn" onClick={tryToken}>Sign in</button>
        <div className="hint">the token your server was started with —
          <code>SKILLLAB_TOKEN</code> · dev default <code>t</code></div>
      </div>
    </section>

    {/* ---------- footer ---------- */}
    <footer className="lp-footer">
      <div className="lp-footer-in">
        <div className="flinks">
          <a href={GITHUB}>GitHub</a>
          <a href={`${GITHUB}/issues`}>Issues</a>
          <a href={`${GITHUB}/blob/main/SPEC.md`}>Spec</a>
          <a href={`${GITHUB}/blob/main/ROADMAP.md`}>Roadmap</a>
        </div>
        <span className="legal">© SkillLab — MIT · preview figures are sample data, not real customer results</span>
      </div>
    </footer>
  </div>;
}
