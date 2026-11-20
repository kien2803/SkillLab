import React, { useEffect, useState } from "react";
import { Link, NavLink, Route, Routes, useParams } from "react-router-dom";

const TOKEN_KEY = "skilllab_token";
const tok = () => localStorage.getItem(TOKEN_KEY) || "";
const api = (p, opts = {}) =>
  fetch("/api/v1" + p, {
    ...opts,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${tok()}`,
      ...(opts.headers || {}),
    },
  }).then((r) => (r.ok ? r.json() : r.json().then((e) => Promise.reject(e.detail || r.status))));

function Nav() {
  const items = [["/", "Overview"], ["/projects", "Research"],
                 ["/explorer", "Web Explorer"], ["/deep", "Deep Research"], ["/skills", "Skill Studio"],
                 ["/blueprints", "Blueprints"], ["/experiments", "Experiments"], ["/proposals", "AI Architect"], ["/failures", "Failures"], ["/releases", "Releases"]];
  const [tk, setTk] = useState(tok());
  return (
    <nav style={{ display: "flex", gap: 16, borderBottom: "1px solid #333",
                  padding: "8px 24px", fontFamily: "monospace" }}>
      <b style={{ marginRight: 16 }}>SkillLab</b>
      {items.map(([to, label]) => (
        <NavLink key={to} to={to} end={to === "/"}
          style={({ isActive }) => ({
            color: isActive ? "#7aa2ff" : "#aaa",
            textDecoration: "none" })}>{label}</NavLink>))}
      <span style={{ flex: 1 }} />
      <input value={tk} placeholder="api token"
        onChange={(e) => { setTk(e.target.value);
          localStorage.setItem(TOKEN_KEY, e.target.value); }}
        style={{ width: 180, background: "#16181d", color: "#ddd",
                 border: "1px solid #333", padding: "2px 6px" }} />
    </nav>);
}

function Overview() {
  const [data, setData] = useState({});
  useEffect(() => {
    Promise.all([api("/projects"), api("/skills"), api("/experiments"),
                 api("/releases")])
      .then(([projects, skills, experiments, releases]) =>
        setData({ projects, skills, experiments, releases }))
      .catch(() => setData({}));
  }, []);
  const cards = [["projects", data.projects], ["skills", data.skills],
                 ["experiments", data.experiments],
                 ["releases", data.releases]];
  return <Page>
    <div style={{ display: "grid", gap: 12,
                  gridTemplateColumns: "repeat(4,1fr)" }}>
      {cards.map(([k, v]) => (
        <div key={k} style={card}>
          <div style={{ fontSize: 28 }}>{v ? v.length : "—"}</div>
          <div style={{ color: "#888" }}>{k}</div></div>))}
    </div></Page>;
}

function Projects() {
  const [list, setList] = useState([]);
  const [sel, setSel] = useState(null);
  useEffect(() => { api("/projects").then(setList).catch(() => {}); }, []);
  return <Page><h2>Research Projects</h2>
    {list.map((p) => (
      <div key={p.id} style={card}>
        <Link to={"#"} onClick={() =>
          api("/projects/" + p.id).then(setSel)}>{p.id}</Link>
        <span style={{ color: "#888" }}> — {p.title} [{p.status}]</span>
      </div>))}
    {sel && <div style={card}>
      <h3>{sel.meta.title || sel.meta.id}</h3>
      <p>{sel.meta.objective}</p>
      <b>Questions</b>
      <ul>{sel.questions.map((q) => (
        <li key={q.id}>{q.id} [{q.status}] {q.question}</li>))}</ul>
      <AddForm ph="new question" onAdd={(v) =>
        api(`/projects/${sel.meta.id}/questions`,
            { method: "POST", body: JSON.stringify({ text: v }) })
          .then(() => api("/projects/" + sel.meta.id).then(setSel))} />
      <b>Findings</b>
      <ul>{sel.findings.map((f) => (
        <li key={f.id}>{f.id} [{f.status}/{f.confidence}] {f.statement}</li>))}
      </ul>
      <AddForm ph="new finding" onAdd={(v) =>
        api(`/projects/${sel.meta.id}/findings`,
            { method: "POST", body: JSON.stringify({ statement: v }) })
          .then(() => api("/projects/" + sel.meta.id).then(setSel))} />
      <AddForm ph="new note title" onAdd={(v) =>
        api(`/projects/${sel.meta.id}/notes`,
            { method: "POST", body: JSON.stringify({ title: v }) })} />
      </div>}
  </Page>;
}

function Explorer() {
  const [q, setQ] = useState("");
  const [res, setRes] = useState([]);
  const [page, setPage] = useState(null);
  const [err, setErr] = useState("");
  const search = () =>
    api("/web-search", { method: "POST", body: JSON.stringify({ query: q }) })
      .then(setRes).catch((e) => setErr(String(e)));
  const open = (url) =>
    api("/web-fetch", { method: "POST", body: JSON.stringify({ url }) })
      .then(setPage).catch((e) => setErr(String(e)));
  return <Page><h2>Web Explorer</h2>
    <input value={q} onChange={(e) => setQ(e.target.value)}
      placeholder="search query" style={{ width: 400, padding: 6 }} />
    <button onClick={search} style={{ marginLeft: 8 }}>Search</button>
    {err && <p style={{ color: "#f88" }}>{err}</p>}
    {res.map((r, i) => (
      <div key={i} style={card}>
        <a href="#" onClick={() => open(r.url)}>{r.title || r.url}</a>
        <div style={{ color: "#888", fontSize: 12 }}>{r.url}</div>
        <div style={{ fontSize: 13 }}>{r.snippet}</div></div>))}
    {page && <div style={card}>
      <h3>{page.title}</h3>
      <div style={{ color: "#888", fontSize: 12 }}>
        {page.final_url} · {page.bytes}B · hash {page.hash}</div>
      <p style={{ fontSize: 13, whiteSpace: "pre-wrap" }}>
        {page.text.slice(0, 4000)}</p></div>}
  </Page>;
}

function Skills() {
  const [list, setList] = useState([]);
  const [pv, setPv] = useState(null);
  useEffect(() => { api("/skills").then(setList).catch(() => {}); }, []);
  return <Page><h2>Skill Studio</h2>
    {list.map((s) => (
      <div key={s.id} style={card}>
        <b>{s.id}</b> [{s.status}]
        {s.variants.map((v) => (
          <span key={v.id} style={{ marginLeft: 8 }}>
            <a href="#" onClick={() =>
              api(`/skills/${s.id}@${v.id}/preview`).then(setPv)}>
              {v.id}</a></span>))}
        </div>))}
    {pv && <div style={card}>
      <h3>{pv.ref} — {pv.entry} ~{pv.tokens} tok</h3>
      <pre style={{ fontSize: 12 }}>{JSON.stringify(pv.fm, null, 1)}</pre>
      <b>Sections</b><ul>{pv.sections.map((s, i) =>
        <li key={i}>{s}</li>)}</ul>
      <b>Resources</b><ul>{pv.resources.map((r, i) =>
        <li key={i}>{r}</li>)}</ul></div>}
  </Page>;
}
function Proposals() {
  const [list, setList] = useState([]);
  const [msg, setMsg] = useState("");
  const load = () => api("/proposals").then(setList).catch(() => {});
  useEffect(load, []);
  const act = (id, a) =>
    api(`/proposals/${id}/${a}`, { method: "POST" })
      .then(() => { setMsg(`${id} ${a}d`); load(); })
      .catch((e) => setMsg(String(e)));
  return <Page><h2>AI Architect — Proposals</h2>
    {msg && <p style={{ color: "#8f8" }}>{msg}</p>}
    {list.map((p) => <div key={p.id} style={card}>
      <b>{p.id}</b> [{p.status}] {p.skill}@{p.variant}
      <div style={{ fontSize: 12, color: "#888" }}>{p.finding}</div>
      <div style={{ fontSize: 13 }}>{p.patch ? p.patch.summary : ""}</div>
      {p.diff_preview
        ? <pre style={{ fontSize: 11, maxHeight: 160, overflow: "auto",
            background: "#0a0c0f", padding: 8 }}>
            {p.diff_preview.slice(0, 3000)}</pre>
        : null}
      {p.status === "pending"
        ? <span><button onClick={() => act(p.id, "approve")}>Approve</button>
          <button onClick={() => act(p.id, "reject")}>Reject</button></span>
        : null}
      {p.status === "approved"
        ? <button onClick={() => act(p.id, "apply")}>Apply</button>
        : null}
    </div>)}</Page>;
}

function Failures() {
  const [list, setList] = useState([]);
  useEffect(() => { api("/failures").then(setList).catch(() => {}); }, []);
  return <Page><h2>Failure Analysis</h2>
    {list.map((f, i) => (
      <div key={i} style={card}>
        <b>{f.run_id}</b> [{f.verdict}] {f.skill_ref}
        {(f.causes || []).map((c, j) => (
          <div key={j} style={{ fontSize: 13, marginTop: 4 }}>
            <b style={{ color: "#f88" }}>{c.category}</b> — {c.hypothesis}
            <div style={{ color: "#888", fontSize: 12 }}>{c.evidence}</div>
          </div>))}
        {(f.proposals || []).map((p, j) => (
          <div key={j} style={{ fontSize: 12, marginTop: 4,
                                color: "#ad7" }}>→ {p.change}</div>))}
      </div>))}</Page>;
}

function Releases() {
  const [list, setList] = useState([]);
  useEffect(() => { api("/releases").then(setList).catch(() => {}); }, []);
  return <Page><h2>Release Center</h2>
    {list.map((r, i) => (
      <div key={i} style={card}>
        <b>{r.skill}@{r.version}</b> — {r.variant} [{r.status}]
        <div style={{ color: "#888", fontSize: 12 }}>{r.changelog}</div>
      </div>))}</Page>;
}

function Experiments() {
  const [list, setList] = useState([]);
  const [msg, setMsg] = useState("");
  const [runs, setRuns] = useState([]);
  const [cmp, setCmp] = useState({});
  const [rep, setRep] = useState({});
  const load = () => {
    api("/experiments").then(setList).catch(() => {});
    api("/runs").then(setRuns).catch(() => {});
  };
  useEffect(load, []);
  const run = (id) =>
    api(`/experiments/${id}/run`, { method: "POST" })
      .then((r) => { setMsg(`${id}: ${r.count} runs`); load(); })
      .catch((e) => setMsg(String(e)));
  const compare = (id) =>
    api(`/experiments/${id}/compare`)
      .then((c) => setCmp({ ...cmp, [id]: c }))
      .catch((e) => setMsg(String(e)));
  const report = (id) =>
    api(`/experiments/${id}/report`)
      .then((r) => setRep({ ...rep, [id]: r.markdown }))
      .catch((e) => setMsg(String(e)));
  return <Page><h2>Experiment Lab</h2>
    {msg && <p style={{ color: "#8f8" }}>{msg}</p>}
    {list.map((e) => <div key={e.id} style={card}>
      <b>{e.id}</b> [{e.status}] {e.title}
      <div style={{ fontSize: 12, color: "#888" }}>
        arms: {e.arms.map((a) => a.name + "=" + (a.skill || "none")).join(", ")}
        · tasks: {e.tasks.join(", ") || "—"}
        · rollouts: {e.rollouts_per_arm}
        · model: {e.fixed ? e.fixed.model : "?"}</div>
      <button onClick={() => run(e.id)}>Run</button>
      <button onClick={() => compare(e.id)} style={{ marginLeft: 6 }}>
        Compare</button>
      <button onClick={() => report(e.id)} style={{ marginLeft: 6 }}>
        Report</button>
      {cmp[e.id] && <table style={{ fontSize: 12, marginTop: 8,
        borderCollapse: "collapse" }}>
        <thead><tr><th style={th}>arm</th>
          {cmp[e.id].tasks.map((t) => <th key={t} style={th}>{t}</th>)}</tr>
        </thead>
        <tbody>{cmp[e.id].arms.map((a) => <tr key={a.name}>
          <td style={td}><b>{a.name}</b>
            <span style={{ color: "#888" }}> {a.skill || "none"}</span></td>
          {cmp[e.id].tasks.map((t) => {
            const c = a.cells[t];
            return <td key={t} style={td}>{c
              ? `${c.mean.toFixed(2)}±${c.stdev.toFixed(2)} (n=${c.n})`
              : "—"}</td>;})}
        </tr>)}</tbody></table>}
      {rep[e.id] && <pre style={{ fontSize: 11, whiteSpace: "pre-wrap",
        maxHeight: 300, overflow: "auto", background: "#0a0c0f",
        padding: 8, marginTop: 8 }}>{rep[e.id]}</pre>}
    </div>)}
    <h3>Recent runs</h3>
    {runs.slice(-10).reverse().map((r) => (
      <div key={r.run_id} style={{ fontSize: 12 }}>
        <Link to={"/runs/" + r.run_id}><code>{r.run_id}</code></Link>
        {" "} [{r.status}] {r.skill_ref}</div>))}
  </Page>;
}

const th = { textAlign: "left", borderBottom: "1px solid #333",
             padding: "2px 10px 2px 0" };
const td = { padding: "2px 14px 2px 0", borderBottom: "1px solid #222" };

function RunDetail() {
  const { rid } = useParams();
  const [d, setD] = useState(null);
  const [art, setArt] = useState(null);
  const [scores, setScores] = useState({});
  const [msg, setMsg] = useState("");
  const [showTr, setShowTr] = useState(false);
  const load = () => api("/runs/" + rid).then(setD)
    .catch((e) => setMsg(String(e)));
  useEffect(load, [rid]);
  if (!d) return <Page><p style={{ color: "#f88" }}>{msg || "loading…"}</p></Page>;
  const { run: r, eval: ev, transcript, artifacts, failure } = d;
  const humanPending = (ev?.checks || []).filter(
    (c) => c.method === "human" && c.status === "pending");
  const openArt = (p) =>
    api(`/runs/${rid}/artifact?path=${encodeURIComponent(p)}`)
      .then(setArt).catch((e) => setMsg(String(e)));
  const score = () => {
    const clean = Object.fromEntries(Object.entries(scores)
      .filter(([, v]) => Number.isFinite(v)));
    api(`/runs/${rid}/eval`,
        { method: "POST",
          body: JSON.stringify({ scores: clean, comments: {} }) })
      .then(() => { setMsg("scores applied"); setScores({}); load(); })
      .catch((e) => setMsg(String(e)));
  };
  const reeval = () =>
    api(`/runs/${rid}/eval`,
        { method: "POST", body: JSON.stringify({ scores: {} }) })
      .then(() => { setMsg("re-evaluated"); load(); })
      .catch((e) => setMsg(String(e)));
  const stats = [["status", r.status],
    ["eval", ev ? ev.status : "—"],
    ["score", ev && ev.rubric_score != null
      ? ev.rubric_score.toFixed(2) : "—"],
    ["turns", r.usage?.turns],
    ["tokens", (r.usage?.input_tokens || 0) + (r.usage?.output_tokens || 0)]];
  return <Page>
    <h2 style={{ fontSize: 16 }}><code>{r.run_id}</code></h2>
    <p style={{ fontSize: 12, color: "#888" }}>
      experiment {r.experiment} · arm {r.arm} · task {r.task} ·
      model {r.model?.name} · mode {r.injection_mode} ·
      skill {r.skill_ref || "none"}</p>
    {msg && <p style={{ color: "#8f8" }}>{msg}</p>}
    {r.error && <p style={{ color: "#f88" }}>run error: {r.error}</p>}
    <div style={{ display: "flex", gap: 12 }}>
      {stats.map(([k, v]) => <div key={k} style={{ ...card, margin: 0,
        minWidth: 90 }}><div style={{ fontSize: 18 }}>{v ?? "—"}</div>
        <div style={{ color: "#888", fontSize: 11 }}>{k}</div></div>)}
    </div>
    <h3>Evaluation</h3>
    {ev ? <>
      <table style={{ fontSize: 12, borderCollapse: "collapse" }}>
        <thead><tr>{["criterion","method","status","score","judge",
          "detail"].map((h) => <th key={h} style={th}>{h}</th>)}</tr></thead>
        <tbody>{ev.checks.map((c) => <tr key={c.id}>
          <td style={td}><b>{c.id}</b></td>
          <td style={td}>{c.method}</td>
          <td style={{ ...td,
            color: c.status === "passed" ? "#8f8"
              : c.status === "pending" ? "#aa5" : "#f88" }}>{c.status}</td>
          <td style={td}>{c.score != null ? c.score.toFixed(2) : "—"}</td>
          <td style={td}>{c.judge_model || "—"}</td>
          <td style={td}>{(c.detail || "").slice(0, 120)}</td>
        </tr>)}</tbody></table>
      <div style={{ marginTop: 8 }}>
        <button onClick={reeval}>Re-evaluate</button>
        {ev.evaluated_at && <span style={{ color: "#888", fontSize: 11,
          marginLeft: 8 }}>evaluated at {ev.evaluated_at}</span>}
      </div>
      {humanPending.length > 0 && <div style={{ ...card, marginTop: 8 }}>
        <b>Human scoring</b>
        {humanPending.map((c) => <div key={c.id} style={{ marginTop: 4 }}>
          <label style={{ fontSize: 12 }}>{c.id}: </label>
          <input type="number" step="0.5" min="0" style={{ width: 70,
            background: "#0a0c0f", color: "#ddd",
            border: "1px solid #333" }}
            value={scores[c.id] ?? ""}
            onChange={(e) => setScores({ ...scores,
              [c.id]: parseFloat(e.target.value) })} />
        </div>)}
        <button onClick={score} style={{ marginTop: 6 }}
          disabled={!Object.keys(scores).length}>Apply scores</button>
      </div>}
    </> : <p style={{ color: "#f88", fontSize: 12 }}>
      no eval.yaml — evaluation missing or pending
      <button onClick={reeval} style={{ marginLeft: 8 }}>Evaluate</button></p>}
    {failure && <>
      <h3>Failure analysis [{failure.verdict}]</h3>
      <table style={{ fontSize: 12, borderCollapse: "collapse" }}>
        <thead><tr>{["category","hypothesis","evidence"].map((h) =>
          <th key={h} style={th}>{h}</th>)}</tr></thead>
        <tbody>{(failure.causes || []).map((c, i) => <tr key={i}>
          <td style={{ ...td, color: "#f88" }}>{c.category}</td>
          <td style={td}>{(c.hypothesis || "").slice(0, 110)}</td>
          <td style={{ ...td, color: "#888" }}>
            {(c.evidence || "").slice(0, 80)}</td>
        </tr>)}</tbody></table></>}
    {r.skill_events?.length > 0 && <>
      <h3>Skill events</h3>
      <table style={{ fontSize: 12, borderCollapse: "collapse" }}>
        <thead><tr>{["turn","event","skill","path"].map((h) =>
          <th key={h} style={th}>{h}</th>)}</tr></thead>
        <tbody>{r.skill_events.map((e, i) => <tr key={i}>
          <td style={td}>{e.t}</td><td style={td}>{e.event}</td>
          <td style={td}>{e.skill || "—"}</td>
          <td style={td}>{e.path || "—"}</td>
        </tr>)}</tbody></table></>}
    {artifacts?.length > 0 && <>
      <h3>Artifacts ({artifacts.length})</h3>
      <ul style={{ fontSize: 12 }}>{artifacts.map((p) =>
        <li key={p}><a href="#" onClick={() => openArt(p)}>
          <code>{p}</code></a></li>)}</ul>
      {art && <pre style={{ fontSize: 11, background: "#0a0c0f",
        padding: 8, maxHeight: 240, overflow: "auto" }}>
        <b>{art.path}</b>{"\n"}{art.text.slice(0, 8000)}</pre>}</>}
    <h3><a href="#" onClick={() => setShowTr(!showTr)}
      style={{ color: "#ddd" }}>Transcript {showTr ? "▾" : "▸"}
      {transcript ? ` (${transcript.length})` : ""}</a></h3>
    {showTr && (transcript || []).map((m, i) => (
      <div key={i} style={{ fontSize: 12, margin: "6px 0",
        borderLeft: "2px solid #333", paddingLeft: 8 }}>
        <b style={{ color: m.role === "assistant" ? "#7aa2ff" : "#888" }}>
          #{i} {m.role}{m.name ? ` [${m.name}]` : ""}</b>
        {m.usage && <span style={{ color: "#666", fontSize: 10,
          marginLeft: 8 }}>in={m.usage.input} out={m.usage.output}</span>}
        {m.role === "assistant" && m.tool_calls
          ? m.tool_calls.map((tc, j) => <div key={j}>
              <b style={{ color: "#ad7" }}>→ {tc.function.name}</b>
              <pre style={{ fontSize: 11, color: "#999", margin: "2px 0",
                whiteSpace: "pre-wrap" }}>
                {tc.function.arguments.slice(0, 600)}</pre></div>)
          : <pre style={{ fontSize: 11, whiteSpace: "pre-wrap",
              margin: "2px 0", color: "#bbb" }}>
              {(m.content || "").slice(0, 3000)}</pre>}
      </div>))}
    {showTr && d.transcript_truncated &&
      <p style={{ color: "#aa5", fontSize: 11 }}>transcript truncated</p>}
  </Page>;
}

function Blueprints() {
  const [projects, setProjects] = useState([]);
  const [sel, setSel] = useState(null);
  const [bpPid, setBpPid] = useState("");
  useEffect(() => { api("/projects").then(setProjects).catch(() => {}); }, []);
  const pick = (pid) => { setBpPid(pid);
    api(`/projects/${pid}/blueprints`).then(setSel).catch(() => setSel([])); };
  return <Page><h2>Blueprints</h2>
    {projects.map((p) => (
      <button key={p.id} onClick={() => pick(p.id)}
        style={{ marginRight: 8 }}>{p.id}</button>))}
    {sel && sel.map((b) => <div key={b.id} style={card}>
      <b>{b.id}</b> [{b.status}] rev {b.rev} — {b.title}
      <div style={{ fontSize: 12, color: "#888" }}>
        generated: {(b.generated_variants || []).join(", ") || "—"}</div>
      <b>Fields</b>
      <ul style={{ fontSize: 12 }}>
        {Object.entries(b.fields || {}).filter(([, v]) =>
          v && (Array.isArray(v) ? v.length : true))
          .map(([k, v]) => <li key={k}><b>{k}</b>: {String(v).slice(0, 90)}
            </li>)}
      </ul>
      <BpEdit pid={bpPid} bid={b.id} fields={b.fields} reload={() => pick(bpPid)} /></div>)}
    {sel && sel.length === 0 && <p style={{ color: "#888" }}>
      no blueprints in this project</p>}
  </Page>;
}

function DeepResearch() {
  const [projects, setProjects] = useState([]);
  const [pid, setPid] = useState("");
  const [obj, setObj] = useState("");
  const [run, setRun] = useState(null);
  const [err, setErr] = useState("");
  useEffect(() => { api("/projects").then(setProjects).catch(() => {}); }, []);
  const start = () =>
    api(`/projects/${pid}/research`,
        { method: "POST", body: JSON.stringify({ objective: obj }) })
      .then(setRun).catch((e) => setErr(String(e)));
  const exec = () => {
    const es = new EventSource(`/api/v1/research/${pid}/${run.id}/stream`);
    es.onmessage = (m) => {
      const s = JSON.parse(m.data);
      setRun((r) => ({ ...r, state: { ...(r.state||{}), ...s } }));
      if (["completed","failed"].includes(s.status)) es.close();
    };
    es.onerror = () => { setErr("stream lost"); es.close(); };
  };
  const show = () =>
    api(`/research/${pid}/${run.id}`).then((s) =>
      setRun({ ...run, state: s })).catch(() => {});
  const st = run && run.state ? run.state : null;
  return <Page><h2>Deep Research</h2>
    <select value={pid} onChange={(e) => setPid(e.target.value)}>
      <option value="">project…</option>
      {projects.map((p) => <option key={p.id} value={p.id}>{p.id}</option>)}
    </select>
    <input value={obj} onChange={(e) => setObj(e.target.value)}
      placeholder="research objective" style={{ width: 420, marginLeft: 8 }} />
    <button onClick={start} disabled={!pid || !obj}>Plan</button>
    {err && <p style={{ color: "#f88" }}>{err}</p>}
    {st && <div style={card}>
      <b>{run.id}</b> [{st.status}] model: {st.model}
      <div style={{ fontSize: 12 }}>queries: {(st.plan.queries || [])
        .join(" · ")}</div>
      {st.status !== "completed" && <>
        <button onClick={exec}>Run (bounded)</button>
        <button onClick={show}>Refresh</button></>}
      {st.report_md && <pre style={{ fontSize: 12, whiteSpace: "pre-wrap",
        maxHeight: 500, overflow: "auto" }}>{st.report_md}</pre>}
    </div>}
  </Page>;
}

function BpEdit({ pid, bid, fields, reload }) {
  const [vals, setVals] = useState({});
  const [msg, setMsg] = useState("");
  const LIST = new Set(["target_users","use_cases","in_scope_tasks",
    "out_of_scope_tasks","trigger_conditions","preconditions",
    "required_context","execution_workflow","decision_rules",
    "tool_requirements","resource_requirements","error_handling",
    "safety_constraints","known_limitations","evaluation_criteria",
    "compatible_environments"]);
  const keys = Object.keys(fields || {});
  const save = () =>
    api(`/projects/${pid}/blueprints/${bid}/fields`,
        { method: "POST", body: JSON.stringify({ fields: vals }) })
      .then(() => { setMsg("saved"); setVals({}); reload(); })
      .catch((e) => setMsg(String(e)));
  return <div style={{ marginTop: 8 }}>
    {keys.map((k) => {
      const isList = LIST.has(k) || Array.isArray(fields[k]);
      const cur = vals[k] !== undefined ? vals[k]
        : (isList ? (fields[k] || []).join("\n") : (fields[k] || ""));
      return <div key={k} style={{ margin: "4px 0" }}>
        <label style={{ fontSize: 11, color: "#888" }}>{k}</label><br/>
        {isList
          ? <textarea rows={3} value={cur} style={{ width: "100%",
              background: "#0a0c0f", color: "#ddd",
              border: "1px solid #333" }}
              onChange={(e) => setVals({ ...vals,
                [k]: e.target.value.split("\n").filter(Boolean) })} />
          : <input value={cur} style={{ width: "100%",
              background: "#0a0c0f", color: "#ddd",
              border: "1px solid #333" }}
              onChange={(e) => setVals({ ...vals, [k]: e.target.value })} />}
      </div>;})}
    <button onClick={save} disabled={!Object.keys(vals).length}>
      Save changes</button>
    {msg && <span style={{ color: "#8f8", marginLeft: 8 }}>{msg}</span>}
  </div>;
}

const card = { border: "1px solid #333", borderRadius: 6, padding: 12,
               margin: "8px 0", background: "#16181d" };
const Page = ({ children }) => (
  <div style={{ padding: 24, fontFamily: "monospace", color: "#ddd",
                background: "#0e1013", minHeight: "100vh" }}>{children}</div>);

export default function App() {
  return (<><Nav /><Routes>
    <Route path="/" element={<Overview />} />
    <Route path="/projects" element={<Projects />} />
    <Route path="/explorer" element={<Explorer />} />
    <Route path="/deep" element={<DeepResearch />} />
    <Route path="/skills" element={<Skills />} />
    <Route path="/blueprints" element={<Blueprints />} />
    <Route path="/experiments" element={<Experiments />} />
    <Route path="/runs/:rid" element={<RunDetail />} />
    <Route path="/proposals" element={<Proposals />} />
    <Route path="/failures" element={<Failures />} />
    <Route path="/releases" element={<Releases />} />
  </Routes></>);
}
// blueprint field editor appended in Blueprints page
