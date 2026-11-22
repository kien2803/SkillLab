import React, { useEffect, useState } from "react";
import { Link, NavLink, Route, Routes, useParams } from "react-router-dom";

import { TOKEN_KEY, tok, api } from "./api.js";
import { SkillEditor } from "./features/skills/SkillEditor.jsx";
import { ExperimentBuilder } from
  "./features/experiments/ExperimentBuilder.jsx";

/* ---------- icons (17px outline, stroke currentColor) ---------- */
const ic = (d) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
    strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"
    aria-hidden="true"><path d={d} /></svg>);
const ICONS = {
  overview: "M3 3h8v8H3zM13 3h8v5h-8zM13 11h8v10h-8zM3 14h8v7H3z",
  research: "M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z",
  explorer: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM3 12h18M12 3c2.5 2.5 3.5 5.5 3.5 9s-1 6.5-3.5 9c-2.5-2.5-3.5-5.5-3.5-9s1-6.5 3.5-9z",
  deep: "M12 3l9 5-9 5-9-5zM3 13l9 5 9-5M3 18l9 5 9-5",
  skills: "M12 3l2.2 4.7 5.1.7-3.7 3.6.9 5.1-4.5-2.4-4.5 2.4.9-5.1L4.8 8.4l5.1-.7z",
  blueprints: "M4 20l1-4L16.5 4.5a2.1 2.1 0 0 1 3 3L8 19zM13 6.5l3.5 3.5",
  experiments: "M9 3h6M10 3v5.5L4.8 18a2 2 0 0 0 1.8 3h10.8a2 2 0 0 0 1.8-3L14 8.5V3M7 15h10",
  regressions: "M4 4v16h16M7 14l4-4 3 3 5-6",
  workspace: "M4 6c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3zM4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3",
  architect: "M6 4a2 2 0 1 0 0 4 2 2 0 0 0 0-4zM18 16a2 2 0 1 0 0 4 2 2 0 0 0 0-4zM6 8v8a4 4 0 0 0 4 4h4M18 4v8a4 4 0 0 1-4 4h-1",
  failures: "M12 4L2.5 20h19zM12 10v4M12 17.5v.5",
  knowledge: "M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2zM4 19V5M8 7h7",
  releases: "M12 3l8 4.5v9L12 21l-8-4.5v-9zM12 12l8-4.5M12 12v9M12 12L4 7.5",
  key: "M14 10a4 4 0 1 0-4 4c.5 0 1-.1 1.4-.3L13 15h2v2h2v2h3v-3.2zM16.5 7.5a1 1 0 1 1 0 .01",
};
const NAV = [
  [["/", "overview", "Home"]],
  [["/skills", "skills", "Skills"],
   ["/suite", "workspace", "Test Suite"]],
  [["/benchmark", "experiments", "Benchmark"]],
  [["/report", "releases", "Report"]],
];

function Rail() {
  const [showTk, setShowTk] = useState(false);
  return (
    <nav className="rail" aria-label="primary">
      <div className="railin">
      <Link to="/" className="mark" title="SkillLab"
        aria-label="SkillLab home">
        <svg viewBox="0 0 30 30" width="30" height="30">
          <path d="M11 4h8M13 4v7.5L5.5 22a3 3 0 0 0 2.6 4.5h13.8A3 3 0 0 0 24.5 22L17 11.5V4"
            fill="none" stroke="var(--accent)" strokeWidth="1.8"
            strokeLinecap="round" strokeLinejoin="round"/>
          <path d="M9 18h12" stroke="var(--accent)" strokeWidth="1.8"
            strokeLinecap="round"/>
        </svg>
      </Link>
      {NAV.map((g, gi) => (
        <React.Fragment key={gi}>
          {gi > 0 && <div className="sep" />}
          {g.map(([to, icn, label]) => (
            <NavLink key={to} to={to} end={to === "/"} title={label}
              aria-label={label}
              className={({ isActive }) => isActive ? "active" : ""}>
              {ic(ICONS[icn])}
            </NavLink>))}
        </React.Fragment>))}
      <div className="end" />
      <button className="link" title="API token" aria-label="API token"
        style={{ color: "var(--muted)", width: 44, height: 38 }}
        onClick={() => setShowTk(!showTk)}>{ic(ICONS.key)}</button>
      {showTk && <TokenIn />}
      </div>
    </nav>);
}

function TokenIn() {
  const [tk, setTk] = useState(tok());
  return (
    <div className="tokpop">
      <label className="small mut">api token<br />
        <input value={tk} placeholder="token" style={{ width: 180 }}
          onChange={(e) => { setTk(e.target.value);
            localStorage.setItem(TOKEN_KEY, e.target.value); }} />
      </label>
    </div>);
}

/* ---------- primitives ---------- */
const POS = new Set(["released","completed","supported","passed","accepted",
  "clean","synced","valid","concluded","answered","ok","generated",
  "validated","graduated","healthy","confirmed"]);
const NEG = new Set(["failed","regressed","rejected","refuted","deprecated",
  "error","drifted","degraded","archived","refuted"]);
const WRN = new Set(["running","testing","validating","investigating",
  "candidate","draft","designed","improving","analyzing","inconclusive",
  "pending","deferred","ready_for_generation","researching","developing",
  "experimenting","designing","proposed","open","active"]);
function Pill({ v }) {
  const c = POS.has(v) ? "pos" : NEG.has(v) ? "neg" : WRN.has(v) ? "warn" : "";
  return <span className={"pill " + c}>{v}</span>;
}
const Page = ({ title, sub, children }) => (
  <div className="canvas">
    <div className="titlerow"><div>
      <h1>{title}</h1>
      {sub && <div className="sub">{sub}</div>}
    </div><div className="sp" /></div>
    {children}
  </div>);
const StatusSel = ({ value, options, onChange }) => (
  <select value={value} onChange={(e) => onChange(e.target.value)}>
    {options.map((o) => <option key={o} value={o}>{o}</option>)}
  </select>);
const Msg = ({ m }) => m
  ? <p className={/^error|denied|not found|invalid|must|cannot|refus/i
      .test(m) ? "msg err" : "msg ok"}>{m}</p> : null;

function AddForm({ ph, onAdd }) {
  const [v, setV] = useState("");
  return <span className="toolbar">
    <input value={v} placeholder={ph} style={{ width: 280 }}
      onChange={(e) => setV(e.target.value)}
      onKeyDown={(e) => e.key === "Enter" && v && (onAdd(v), setV(""))} />
    <button disabled={!v} onClick={() => { onAdd(v); setV(""); }}>+</button>
  </span>;
}

/* ---------- pages ---------- */
const PHASES = ["discover","research","design","create","experiment",
  "analyze","improve","validate","release","learn"];

/* The product workflow: import → suite → benchmark → analyze →
   improve → validate → report. Each step shows done/current/todo
   state computed from real lab data — never fabricated. */
const STEPS = [
  { n: 1, title: "Import skill", to: "/skills",
    hint: "import or register the skill to benchmark" },
  { n: 2, title: "Create test suite", to: "/suite",
    hint: "tasks + rubrics the agent is scored on" },
  { n: 3, title: "Run benchmark", to: "/benchmark",
    hint: "baseline vs skill, controlled rollouts" },
  { n: 4, title: "Analyze results", to: "/benchmark",
    hint: "score matrix, activation, per-task outcomes" },
  { n: 5, title: "Improve skill", to: "/skills",
    hint: "edit files → a new variant (versions immutable)" },
  { n: 6, title: "Validate new version", to: "/benchmark",
    hint: "regression suite: old vs new variant" },
  { n: 7, title: "Export report", to: "/report",
    hint: "evidence-based quality report for clients" },
];

function Home() {
  const [d, setD] = useState(null);
  useEffect(() => {
    Promise.all([api("/skills"), api("/tasks"), api("/experiments"),
                 api("/regressions"), api("/releases"), api("/status"),
                 api("/runs")])
      .then(([skills, tasks, exps, regs, rels, st, runs]) => setD(
        { skills, tasks, exps, regs, rels, st, runs }))
      .catch(() => setD({}));
  }, []);
  if (!d) return <Page title="SkillLab" sub="loading…" />;
  const analyzed = (d.exps || []).some((e) =>
    ["analyzed", "concluded"].includes(e.status));
  const hasEvals = (d.runs || []).length > 0 && analyzed;
  const multiVariant = (d.skills || []).some((s) =>
    (s.variants || []).length > 1);
  const done = [
    (d.skills || []).length > 0,          // 1 import
    (d.tasks || []).length > 0,           // 2 suite
    (d.runs || []).length > 0,            // 3 benchmark
    hasEvals,                             // 4 analyze
    multiVariant,                         // 5 improve
    (d.regs || []).length > 0,            // 6 validate
    (d.rels || []).length > 0,            // 7 report
  ];
  const cur = done.findIndex((x) => !x);
  return <Page title="SkillLab"
    sub="skill benchmarking & QA — prove the skill helps">
    <div className="steps" role="list">
      {STEPS.map((s, i) => {
        const state = done[i] ? "done"
          : (i === cur || (cur === -1 && i === 6)) ? "cur" : "todo";
        return <Link key={s.n} to={s.to}
          className={"step " + state}>
          <span className="step-n">{done[i] ? "✓" : s.n}</span>
          <div>
            <b>{s.title}</b>
            <div className="small mut">{s.hint}</div>
          </div>
          {state === "cur" && cur !== -1 &&
            <span className="pill acc">next</span>}
        </Link>; })}
    </div>
    {cur === -1 && <div className="card">
      <b className="ok">Full cycle complete.</b>
      <div className="small mut">Import a new skill or a new version to
        start another benchmark cycle.</div>
    </div>}
    <div className="kpis">
      {[["skills", (d.skills || []).length],
        ["tasks", (d.tasks || []).length],
        ["benchmarks", (d.exps || []).length],
        ["regressions", (d.regs || []).length],
        ["runs", (d.runs || []).length],
        ["releases", (d.rels || []).length]]
       .map(([k, v]) => (
        <div key={k}><div className="k">{k}</div>
          <div className="v num">{v}</div></div>))}
    </div>
    {d.st?.model === "mock" && <div className="card">
      <span className="pill warn">model: mock</span>
      <span className="small mut" style={{ marginLeft: 8 }}>
        benchmark results are deterministic simulations — set a real
        model in lab.yaml for production evidence.</span>
    </div>}
    {(d.runs || []).length > 0 && <div className="card">
      <h3>Recent runs</h3>
      <div className="rows">{d.runs.slice(-6).reverse().map((r) =>
        <div key={r.run_id} className="r">
          <Link to={"/runs/" + r.run_id}><code>{r.run_id}</code></Link>
          <Pill v={r.status} />
          <span className="mut small">{r.skill_ref}</span>
        </div>)}</div>
    </div>}
  </Page>;
}

function Projects() {
  const [list, setList] = useState([]);
  const [sel, setSel] = useState(null);
  const [msg, setMsg] = useState("");
  const [link, setLink] = useState({ qid: "", field: "findings",
    ref: "" });
  const load = () => api("/projects").then(setList).catch(() => {});
  useEffect(() => { load(); }, []);
  const reload = (pid) => api("/projects/" + pid).then(setSel)
    .catch((e) => setMsg(String(e)));
  const post = (url, body) =>
    api(url, { method: "POST", body: JSON.stringify(body || {}) })
      .then(() => reload(sel.meta.id))
      .catch((e) => setMsg(String(e)));
  const pstat = (pid, s) =>
    api(`/projects/${pid}/status`,
        { method: "POST", body: JSON.stringify({ status: s }) })
      .then(load).then(() => sel && reload(sel.meta.id))
      .catch((e) => setMsg(String(e)));
  const del = (pid) => {
    if (!window.confirm(`delete empty draft '${pid}'?`)) return;
    api(`/projects/${pid}/delete`,
        { method: "POST", body: JSON.stringify({ confirm: true }) })
      .then(() => { setSel(null); load(); })
      .catch((e) => setMsg(String(e)));
  };
  return <Page title="Research" sub="projects, questions, evidence">
    <Msg m={msg} />
    <div className="toolbar">
      <AddForm ph="new project id" onAdd={(v) =>
        api("/projects", { method: "POST",
          body: JSON.stringify({ id: v, title: v }) })
          .then(load).catch((e) => setMsg(String(e)))} />
    </div>
    <div className="card rows" style={{ padding: "8px 24px" }}>
      {list.map((p) => (
        <div key={p.id} className="r">
          <a href="#" onClick={() => reload(p.id)}><b>{p.id}</b></a>
          <Pill v={p.status} />
          <span className="mut small">{p.title}</span>
          <span className="sp" style={{ flex: 1 }} />
          <StatusSel value={p.status}
            options={["draft","active","researching","designing",
              "developing","experimenting","validating","completed",
              "archived"]}
            onChange={(s) => pstat(p.id, s)} />
          {p.status === "draft" &&
            <button onClick={() => del(p.id)}>delete</button>}
        </div>))}
    </div>
    {sel && <div className="card">
      <h3>{sel.meta.title || sel.meta.id}{" "}<Pill v={sel.meta.status} /></h3>
      <p className="small mut">{sel.meta.objective}</p>
      <b>Questions ({sel.questions.length})</b>
      <div className="rows small">
        {sel.questions.map((q) => (
          <div key={q.id} className="r">
            <code className="mut">{q.id}</code> {q.question}
            <StatusSel value={q.status}
              options={["open","investigating","answered","deferred"]}
              onChange={(s) => post(
                `/projects/${sel.meta.id}/questions/${q.id}/status`,
                { status: s })} />
            {(q.findings.length + q.experiments.length) > 0 &&
              <span className="mut">→
                {" "}{q.findings.concat(q.experiments).join(", ")}</span>}
          </div>))}
      </div>
      <AddForm ph="new question" onAdd={(v) =>
        post(`/projects/${sel.meta.id}/questions`, { text: v })} />
      <div className="toolbar">
        <span className="mut">link</span>
        <select value={link.qid}
          onChange={(e) => setLink({ ...link, qid: e.target.value })}>
          <option value="">question…</option>
          {sel.questions.map((q) =>
            <option key={q.id} value={q.id}>{q.id}</option>)}
        </select>
        <select value={link.field}
          onChange={(e) => setLink({ ...link, field: e.target.value })}>
          <option value="findings">finding</option>
          <option value="experiments">experiment</option>
        </select>
        <input value={link.ref} placeholder="ref id" style={{ width: 160 }}
          onChange={(e) => setLink({ ...link, ref: e.target.value })} />
        <button disabled={!link.qid || !link.ref}
          onClick={() => post(
            `/projects/${sel.meta.id}/questions/${link.qid}/link`,
            link)}>Link</button>
      </div>
      <b>Findings ({sel.findings.length})</b>
      <div className="rows small">
        {sel.findings.map((f) => (
          <div key={f.id} className="r">
            <code className="mut">{f.id}</code>
            <span className="pill acc">{f.kind}</span>
            <span className="mut">{f.confidence}</span>
            <span style={{ flex: 1 }}>{f.statement}</span>
            <StatusSel value={f.status}
              options={["candidate","supported","refuted","inconclusive"]}
              onChange={(s) => post(
                `/projects/${sel.meta.id}/findings/${f.id}/status`,
                { status: s })} />
          </div>))}
      </div>
      <AddForm ph="new finding" onAdd={(v) =>
        post(`/projects/${sel.meta.id}/findings`, { statement: v })} />
      <b>Sources ({sel.sources.length})</b>
      <div className="rows small">
        {sel.sources.map((s) => (
          <div key={s.id} className="r" style={{ alignItems: "baseline" }}>
            <code className="mut">{s.id}</code>
            <span className="pill">{s.type}</span>
            <span>{s.title}
              {s.url && <span className="mut"> · {s.url}</span>}</span>
            {s.annotations.map((a, i) =>
              <span key={i} className="ok small">note: {a}</span>)}
          </div>))}
      </div>
      <SrcForm pid={sel.meta.id} onDone={() => reload(sel.meta.id)}
        onErr={setMsg} />
      <b>Decisions ({sel.decisions.length})</b>
      <div className="rows small">
        {sel.decisions.map((d) => (
          <div key={d.id} className="r" style={{ alignItems: "baseline" }}>
            <code className="mut">{d.id}</code>
            <span style={{ flex: 1 }}>{d.decision}
              {d.rationale && <span className="mut"> · {d.rationale}</span>}
            </span>
            <StatusSel value={d.status}
              options={["proposed","accepted","rejected","superseded"]}
              onChange={(s) => post(
                `/projects/${sel.meta.id}/decisions/${d.id}/status`,
                { status: s })} />
          </div>))}
      </div>
      <AddForm ph="new decision" onAdd={(v) =>
        post(`/projects/${sel.meta.id}/decisions`, { decision: v })} />
      <b>Notes ({sel.notes.length})</b>
      <div className="rows small">
        {sel.notes.map((n) => (
          <div key={n.id} className="r">
            <code>{n.id}</code><span className="mut">{n.created}</span>
          </div>))}
      </div>
      <AddForm ph="new note title" onAdd={(v) =>
        post(`/projects/${sel.meta.id}/notes`, { title: v })} />
    </div>}
  </Page>;
}

function SrcForm({ pid, onDone, onErr }) {
  const [f, setF] = useState({ type: "note", title: "", url: "",
    author: "" });
  return <div className="toolbar">
    <select value={f.type}
      onChange={(e) => setF({ ...f, type: e.target.value })}>
      {["url","doc","note","paper","other"].map((t) =>
        <option key={t} value={t}>{t}</option>)}
    </select>
    <input value={f.title} placeholder="title" style={{ width: 200 }}
      onChange={(e) => setF({ ...f, title: e.target.value })} />
    {f.type === "url" &&
      <input value={f.url} placeholder="url" style={{ width: 200 }}
        onChange={(e) => setF({ ...f, url: e.target.value })} />}
    <input value={f.author} placeholder="author" style={{ width: 120 }}
      onChange={(e) => setF({ ...f, author: e.target.value })} />
    <button disabled={!f.title} onClick={() =>
      api(`/projects/${pid}/sources`,
          { method: "POST", body: JSON.stringify(f) })
        .then(onDone).catch((e) => onErr(String(e)))}>Add source</button>
  </div>;
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
  return <Page title="Web Explorer" sub="offline web cache & fetch">
    <div className="toolbar">
      <input value={q} onChange={(e) => setQ(e.target.value)}
        placeholder="search query" style={{ width: 400 }} />
      <button onClick={search}>Search</button>
    </div>
    <Msg m={err} />
    {res.map((r, i) => (
      <div key={i} className="card">
        <a href="#" onClick={() => open(r.url)}>{r.title || r.url}</a>
        <div className="small mut">{r.url}</div>
        <div className="small">{r.snippet}</div></div>))}
    {page && <div className="card">
      <h3>{page.title}</h3>
      <div className="small mut num">
        {page.final_url} · {page.bytes}B · hash {page.hash}</div>
      <pre className="dump">{page.text.slice(0, 4000)}</pre></div>}
  </Page>;
}

function Skills() {
  const [list, setList] = useState([]);
  const [pv, setPv] = useState(null);
  const [panel, setPanel] = useState(null);   // {kind, data}
  const [msg, setMsg] = useState("");
  const [newSk, setNewSk] = useState("");
  const [imp, setImp] = useState("");
  const [editing, setEditing] = useState(null); // "skill@variant"
  const load = () => api("/skills").then(setList).catch(() => {});
  useEffect(() => { load(); }, []);
  const show = (kind, p) =>
    p.then((d) => setPanel({ kind, data: d }))
      .catch((e) => setMsg(String(e)));
  const suggest = (ref) =>
    api(`/skills/${ref}/proposals`, { method: "POST" })
      .then((ps) => setPanel({ kind: "proposals", data: ps }))
      .catch((e) => setMsg(String(e)));
  const upload = (ref, file) => {
    const fd = new FormData();
    fd.append("file", file);
    fetch(`/api/v1/skills/${ref}/resources`, { method: "POST",
      headers: { Authorization: `Bearer ${tok()}` }, body: fd })
      .then((r) => r.ok ? r.json() : r.json().then((e) =>
        Promise.reject(e.detail)))
      .then((d) => setMsg(`resource → ${d.path}`))
      .catch((e) => setMsg(String(e)));
  };
  if (editing)
    return <Page title="Skill Studio" sub="editor">
      <SkillEditor skillRef={editing}
        onClose={() => { setEditing(null); load(); }} /></Page>;
  return <Page title="Skill Management" sub="import, browse, edit, version, compare">
    <Msg m={msg} />
    <div className="card">
      <h3>Registry ops</h3>
      <div className="toolbar">
        <input value={newSk} placeholder="new skill id"
          onChange={(e) => setNewSk(e.target.value)} />
        <button disabled={!newSk} onClick={() =>
          api("/skills", { method: "POST",
            body: JSON.stringify({ id: newSk }) })
            .then(() => { setMsg(`created ${newSk}`); setNewSk("");
              load(); })
            .catch((e) => setMsg(String(e)))}>New</button>
        <input value={imp} placeholder="path or git url[#subdir]"
          style={{ width: 260 }}
          onChange={(e) => setImp(e.target.value)} />
        <button disabled={!imp} onClick={() =>
          api("/skills/import", { method: "POST",
            body: JSON.stringify({ src: imp }) })
            .then((d) => { setMsg(`imported → ${d.path}`); load(); })
            .catch((e) => setMsg(String(e)))}>Import</button>
        <button onClick={() => show("scan", api("/skill-scan"))}>
          Scan agent dirs</button>
      </div>
    </div>
    {list.map((s) => (
      <div key={s.id} className="card">
        <b>{s.id}</b> <Pill v={s.status} />
        <button style={{ marginLeft: 8 }} onClick={() =>
          show("grad", api(`/skills/${s.id}/graduation`))}>
          Graduation</button>
        <div className="toolbar">
          {s.variants.map((v) => (
            <span key={v.id}>
              <a href="#" onClick={() =>
                api(`/skills/${s.id}@${v.id}/preview`)
                  .then((d) => { setPv(d); setPanel(null); })}>
                {v.id}</a>
              {" "}[<a href="#" onClick={() =>
                setEditing(`${s.id}@${v.id}`)}>edit</a>]
              {" "}[<a href="#" onClick={() =>
                show("check", api(`/skills/${s.id}@${v.id}/check`))}>
                check</a>]
              {" "}[<a href="#" onClick={() =>
                show("trace", api(`/trace/${s.id}@${v.id}`))}>
                trace</a>]
              {" "}[<a href="#" onClick={() =>
                suggest(`${s.id}@${v.id}`)}>propose</a>]
              {" "}<label className="small mut">
                <input type="file" style={{ display: "none" }}
                  onChange={(e) => e.target.files[0] &&
                    upload(`${s.id}@${v.id}`, e.target.files[0])} />
                <u style={{ cursor: "pointer" }}>+resource</u></label>
            </span>))}
        </div>
      </div>))}
    {panel && <div className="card">
      {panel.kind === "grad" && <>
        <h3>Graduation · {panel.data.skill_id}
          {" "}({panel.data.n_runs} runs)</h3>
        <div className="small num">
          activation: {panel.data.activation_rate != null
            ? (panel.data.activation_rate * 100).toFixed(0) + "%" : "\u2014"}
          {" · "}false: {panel.data.false_activation_rate != null
            ? (panel.data.false_activation_rate * 100).toFixed(0) + "%"
            : "\u2014"}</div>
        {Object.entries(panel.data.task_deltas || {}).map(([t, d]) =>
          <div key={t} className="small num">
            Δ {t}: {d > 0 ? "+" : ""}{d.toFixed(2)}</div>)}
        <table className="tbl mt">
          <tbody>{panel.data.verdicts.map(([name, ok, detail], i) =>
            <tr key={i}>
              <td className={ok === false ? "bad" : ok === true ? "ok"
                : "warn"}>{ok == null ? "?" : ok ? "PASS" : "FAIL"}</td>
              <td><b>{name}</b></td>
              <td className="mut">{detail}</td>
            </tr>)}</tbody></table></>}
      {panel.kind === "check" && <>
        <h3>Skill check</h3>
        <div className="rows small">{panel.data.map((f, i) =>
          <div key={i} className={f.severity === "error" ? "r bad" : "r warn"}>
            [{f.severity}] {f.check}: {f.message}</div>)}
          {!panel.data.length && <div className="r ok">clean</div>}</div></>}
      {panel.kind === "proposals" && <>
        <h3>Proposals created</h3>
        <div className="rows small">{panel.data.map((p) =>
          <div key={p.id} className="r">{p.id} · {p.patch?.summary ||
            p.finding}</div>)}
          {!panel.data.length && <div className="r mut">
            no proposals generated</div>}</div>
        {panel.data.length > 0 && <div className="small mut">
          review on the AI Architect page</div>}</>}
      {panel.kind === "trace" && <TraceView t={panel.data} />}
      {panel.kind === "scan" && <>
        <h3>Discovered skills</h3>
        <div className="rows small">{panel.data.map((s, i) =>
          <div key={i} className="r"><b>{s.name}</b>
            <span className="mut"> · {s.path}</span></div>)}
          {!panel.data.length && <div className="r mut">none found</div>}
        </div></>}
    </div>}
    {pv && <div className="card">
      <h3>{pv.ref} · {pv.entry} ~{pv.tokens} tok</h3>
      <pre className="dump">{JSON.stringify(pv.fm, null, 1)}</pre>
      <b>Sections</b><ul>{pv.sections.map((s, i) =>
        <li key={i}>{s}</li>)}</ul>
      <b>Resources</b><ul>{pv.resources.map((r, i) =>
        <li key={i}>{r}</li>)}</ul></div>}
  </Page>;
}

function TraceView({ t }) {
  const findings = t.findings || [], questions = t.questions || [],
        experiments = t.experiments || [], runs = t.runs || [],
        insights = t.insights || [];
  return <div>
    <h3>Trace: {t.skill}@{t.variant}</h3>
    {t.blueprint
      ? <div>blueprint: <b>{t.blueprint.project}/{t.blueprint.id}</b>
          {" "}r{t.blueprint.rev} (now r{t.blueprint.rev_current})
          {" "}[{t.blueprint.status}] · project: {t.project}</div>
      : <div className="mut">no blueprint provenance</div>}
    {findings.length > 0 && <div>findings: {findings.map((f) =>
      <span key={f.id} style={{ marginRight: 8 }}>
        {f.id}[{f.status}]</span>)}</div>}
    {questions.length > 0 && <div>questions: {questions.map((q) =>
      <span key={q.id} style={{ marginRight: 8 }}>
        {q.id}[{q.status}]</span>)}</div>}
    {experiments.length > 0 && <div>experiments:
      {" "}{experiments.join(", ")}</div>}
    {runs.length > 0 && <div>runs ({runs.length}):
      {" "}{runs.slice(0, 6).map((r) =>
        <Link key={r} to={"/runs/" + r} style={{ marginRight: 6 }}>
          <code>{r}</code></Link>)}
      {runs.length > 6 && "…"}</div>}
    {insights.length > 0 && <div>insights: {insights.map((i) =>
      <span key={i.id} style={{ marginRight: 8 }}>
        {i.id}[{i.status}/{i.kind}]</span>)}</div>}
  </div>;
}

function Proposals() {
  const [list, setList] = useState([]);
  const [msg, setMsg] = useState("");
  const load = () => api("/proposals").then(setList).catch(() => {});
  useEffect(() => { load(); }, []);
  const act = (id, a) =>
    api(`/proposals/${id}/${a}`, { method: "POST" })
      .then(() => { setMsg(`${id} ${a}d`); load(); })
      .catch((e) => setMsg(String(e)));
  return <Page title="AI Architect" sub="proposal → approve → apply gate">
    <Msg m={msg} />
    {list.map((p) => <div key={p.id} className="card">
      <b>{p.id}</b> <Pill v={p.status} /> {p.skill}@{p.variant}
      <div className="small mut">{p.finding}</div>
      <div className="small">{p.patch ? p.patch.summary : ""}</div>
      {p.diff_preview && <pre className="dump">
        {p.diff_preview.slice(0, 3000)}</pre>}
      {p.status === "pending" &&
        <div className="toolbar">
          <button className="primary"
            onClick={() => act(p.id, "approve")}>Approve</button>
          <button onClick={() => act(p.id, "reject")}>Reject</button></div>}
      {p.status === "approved" &&
        <div className="toolbar">
          <button className="primary"
            onClick={() => act(p.id, "apply")}>Apply</button></div>}
    </div>)}</Page>;
}

function Failures() {
  const [list, setList] = useState([]);
  const [rid, setRid] = useState("");
  const [cand, setCand] = useState({});
  const [msg, setMsg] = useState("");
  const load = () => api("/failures").then(setList).catch(() => {});
  useEffect(() => { load(); }, []);
  const analyze = () =>
    api(`/failures/${rid}`, { method: "POST" })
      .then(() => { setMsg(`analyzed ${rid}`); setRid(""); load(); })
      .catch((e) => setMsg(String(e)));
  const candidate = (run_id) =>
    api(`/failures/${run_id}/candidate`,
        { method: "POST",
          body: JSON.stringify({ variant: cand[run_id] }) })
      .then((d) => setMsg(`candidate → ${d.path}`))
      .catch((e) => setMsg(String(e)));
  return <Page title="Failure Analysis"
    sub="first observable failure → categorized cause → candidate">
    <Msg m={msg} />
    <div className="toolbar">
      <input value={rid} placeholder="run id to analyze"
        style={{ width: 340 }}
        onChange={(e) => setRid(e.target.value)} />
      <button onClick={analyze} disabled={!rid}>Analyze run</button>
    </div>
    {list.map((f, i) => (
      <div key={i} className="card">
        <code><b>{f.run_id}</b></code> <Pill v={f.verdict} />
        <span className="mut"> {f.skill_ref}</span>
        {(f.causes || []).map((c, j) => (
          <div key={j} className="mt">
            <b className="bad">{c.category}</b> · {c.hypothesis}
            <div className="small mut">{c.evidence}</div>
          </div>))}
        {(f.proposals || []).map((p, j) => (
          <div key={j} className="small ok mt">→ {p.change}</div>))}
        <div className="toolbar">
          <span className="mut">candidate variant</span>
          <input value={cand[f.run_id] || ""} placeholder="new variant id"
            style={{ width: 140 }}
            onChange={(e) => setCand({ ...cand,
              [f.run_id]: e.target.value })} />
          <button disabled={!cand[f.run_id]}
            onClick={() => candidate(f.run_id)}>Create candidate</button>
          <span className="mut"> clones variant +
            PROPOSALS.md improvement plan</span>
        </div>
      </div>))}</Page>;
}

function Releases() {
  const [list, setList] = useState([]);
  const [skills, setSkills] = useState([]);
  const [det, setDet] = useState(null);
  const [form, setForm] = useState({ skill: "", version: "",
    variant: "", changelog: "" });
  const [msg, setMsg] = useState("");
  const load = () => api("/releases").then(setList).catch(() => {});
  useEffect(() => { load();
    api("/skills").then(setSkills).catch(() => {}); }, []);
  const open = (r) =>
    api(`/releases/${r.skill}/${r.version}`).then(setDet)
      .catch((e) => setMsg(String(e)));
  const create = () =>
    api("/releases", { method: "POST", body: JSON.stringify(form) })
      .then(() => { setMsg(`created ${form.skill}@${form.version}`);
        setForm({ ...form, version: "", changelog: "" }); load(); })
      .catch((e) => setMsg(String(e)));
  const setStatus = (r, status) =>
    api(`/releases/${r.skill}/${r.version}/status`,
        { method: "POST", body: JSON.stringify({ status }) })
      .then(() => { setMsg(`${r.skill}@${r.version} → ${status}`);
        setDet(null); load(); })
      .catch((e) => setMsg(String(e)));
  const NEXT = { draft: ["candidate"], candidate: ["validated", "draft"],
    validated: ["released", "candidate"], released: ["deprecated"],
    deprecated: [] };
  const variants = (skills.find((s) => s.id === form.skill) || {})
    .variants || [];
  return <Page title="Release Center" sub="checklist-gated shipping">
    <Msg m={msg} />
    <div className="card">
      <h3>New release</h3>
      <div className="toolbar">
        <select value={form.skill}
          onChange={(e) => setForm({ ...form, skill: e.target.value,
            variant: "" })}>
          <option value="">skill…</option>
          {skills.map((s) => <option key={s.id}
            value={s.id}>{s.id}</option>)}
        </select>
        <select value={form.variant}
          onChange={(e) => setForm({ ...form, variant: e.target.value })}>
          <option value="">variant…</option>
          {variants.map((v) => <option key={v.id}
            value={v.id}>{v.id}</option>)}
        </select>
        <input value={form.version} placeholder="version (e.g. 1.0.0)"
          onChange={(e) => setForm({ ...form, version: e.target.value })} />
        <input value={form.changelog} placeholder="changelog"
          style={{ width: 260 }}
          onChange={(e) => setForm({ ...form,
            changelog: e.target.value })} />
        <button className="primary" onClick={create}
          disabled={!form.skill || !form.variant || !form.version}>
          Create draft</button>
      </div>
    </div>
    <div className="card rows" style={{ padding: "8px 24px" }}>
      {list.map((r, i) => (
        <div key={i} className="r">
          <a href="#" onClick={() => open(r)}>
            <b>{r.skill}@{r.version}</b></a>
          <span className="mut">{r.variant}</span>
          <Pill v={r.status} />
          <span className="mut small" style={{ flex: 1 }}>{r.changelog}</span>
          {(NEXT[r.status] || []).map((s) => (
            <button key={s} onClick={() => setStatus(r, s)}>→ {s}</button>))}
        </div>))}
    </div>
    {det && <div className="card">
      <h3>{det.release.skill}@{det.release.version} · checklist</h3>
      <table className="tbl">
        <thead><tr>{["check","required","ok","detail"].map((h) =>
          <th key={h}>{h}</th>)}</tr></thead>
        <tbody>{det.checklist.map((c) => <tr key={c.id}>
          <td><b>{c.id}</b></td>
          <td>{c.required ? "yes" : "no"}</td>
          <td className={c.ok ? "ok" : "bad"}>{c.ok ? "yes" : "no"}</td>
          <td className="mut">{c.detail}</td>
        </tr>)}</tbody></table>
      {det.release.released_at && <p className="small mut">
        released at {det.release.released_at}</p>}
    </div>}
  </Page>;
}

function Knowledge() {
  const [list, setList] = useState([]);
  const [det, setDet] = useState(null);
  const [form, setForm] = useState({ title: "", evidence: "" });
  const [msg, setMsg] = useState("");
  const load = () => api("/insights").then(setList).catch(() => {});
  useEffect(() => { load(); }, []);
  const open = (i) => api("/insights/" + i.id).then(setDet)
    .catch((e) => setMsg(String(e)));
  const create = () =>
    api("/insights", { method: "POST", body: JSON.stringify(form) })
      .then(() => { setMsg(`insight '${form.title}' created`);
        setForm({ title: "", evidence: "" }); load(); })
      .catch((e) => setMsg(String(e)));
  const act = (id, a) =>
    api(`/insights/${id}/${a}`, { method: "POST" })
      .then(() => { setMsg(`${id}: ${a} ok`); setDet(null); load(); })
      .catch((e) => setMsg(String(e)));
  return <Page title="Knowledge Base" sub="insights → principles">
    <Msg m={msg} />
    <div className="card">
      <h3>New insight</h3>
      <div className="toolbar">
        <input value={form.title} placeholder="title" style={{ width: 300 }}
          onChange={(e) => setForm({ ...form, title: e.target.value })} />
        <input value={form.evidence}
          placeholder="evidence (experiment/run id)" style={{ width: 300 }}
          onChange={(e) => setForm({ ...form, evidence: e.target.value })} />
        <button onClick={create} disabled={!form.title}>Create</button>
      </div>
    </div>
    <div className="card rows" style={{ padding: "8px 24px" }}>
      {list.map((i) => <div key={i.id} className="r">
        <a href="#" onClick={() => open(i)}><b>{i.id}</b></a>
        <span className="pill">[{i.kind}]</span>
        <Pill v={i.status} />
        <span className="mut">{i.confidence}</span>
        <span className="mut small" style={{ flex: 1 }}>
          evidence: {(i.evidence || []).join(", ") || "\u2014"}</span>
        {i.kind === "insight" && <>
          {i.status !== "confirmed" &&
            <button onClick={() => act(i.id, "confirm")}>Confirm</button>}
          {i.status !== "refuted" &&
            <button onClick={() => act(i.id, "refute")}>Refute</button>}
          {i.status === "confirmed" &&
            <button className="primary"
              onClick={() => act(i.id, "promote")}>Promote</button>}
        </>}
      </div>)}
    </div>
    {det && <div className="card">
      <h3>{det.id} <span className="pill">{det.kind}</span></h3>
      <table className="tbl">
        <tbody>{Object.entries(det.frontmatter).map(([k, v]) =>
          <tr key={k}>
            <td className="mut">{k}</td>
            <td>{Array.isArray(v) ? v.join(", ") : String(v)}</td>
          </tr>)}</tbody></table>
      <pre className="dump">{det.body}</pre>
    </div>}
  </Page>;
}

function RegressionsBody() {
  const [list, setList] = useState([]);
  const [skills, setSkills] = useState([]);
  const [det, setDet] = useState(null);
  const [msg, setMsg] = useState("");
  const [form, setForm] = useState({ skill: "", baseline: "",
    candidate: "", tasks: "default", mode: "", rollouts: "",
    model: "" });
  const load = () => api("/regressions").then(setList).catch(() => {});
  useEffect(() => { load();
    api("/skills").then(setSkills).catch(() => {}); }, []);
  const open = (id) => api("/regressions/" + id).then(setDet)
    .catch((e) => setMsg(String(e)));
  const run = () => {
    const body = { skill: form.skill, baseline: form.baseline,
      candidate: form.candidate, tasks: form.tasks || "default" };
    if (form.mode) body.mode = form.mode;
    if (form.model) body.model = form.model;
    if (form.rollouts) body.rollouts = parseInt(form.rollouts, 10);
    api("/regressions", { method: "POST", body: JSON.stringify(body) })
      .then((r) => { setMsg(`job ${r.job} — ` +
        `${r.planned} rollouts queued`); load(); })
      .catch((e) => setMsg(String(e)));
  };
  const variants = (skills.find((s) => s.id === form.skill) || {})
    .variants || [];
  const fmt = (m, k, pct) => m && m[k] != null
    ? (pct ? (m[k] * 100).toFixed(0) + "%"
      : typeof m[k] === "number" ? m[k].toFixed(2) : m[k])
    : "\u2014";
  return <>
    <Msg m={msg} />
    <div className="card">
      <h3>Run regression</h3>
      <div className="toolbar">
        <select value={form.skill}
          onChange={(e) => setForm({ ...form, skill: e.target.value,
            baseline: "", candidate: "" })}>
          <option value="">skill…</option>
          {skills.map((s) => <option key={s.id}
            value={s.id}>{s.id}</option>)}
        </select>
        <select value={form.baseline}
          onChange={(e) => setForm({ ...form, baseline: e.target.value })}>
          <option value="">baseline…</option>
          {variants.map((v) => <option key={v.id}
            value={v.id}>{v.id}</option>)}
        </select>
        <select value={form.candidate}
          onChange={(e) => setForm({ ...form, candidate: e.target.value })}>
          <option value="">candidate…</option>
          {variants.filter((v) => v.id !== form.baseline).map((v) =>
            <option key={v.id} value={v.id}>{v.id}</option>)}
        </select>
        <input value={form.tasks} placeholder="tasks (default)"
          onChange={(e) => setForm({ ...form, tasks: e.target.value })} />
        <select value={form.mode}
          onChange={(e) => setForm({ ...form, mode: e.target.value })}>
          <option value="">mode…</option>
          <option value="available">available</option>
          <option value="injected">injected</option>
        </select>
        <input value={form.rollouts} placeholder="rollouts" type="number"
          style={{ width: 80 }}
          onChange={(e) => setForm({ ...form, rollouts: e.target.value })} />
        <input value={form.model} placeholder="model (default: lab)"
          style={{ width: 170 }}
          onChange={(e) => setForm({ ...form, model: e.target.value })} />
        <button className="primary" onClick={run}
          disabled={!form.skill || !form.baseline || !form.candidate}>
          Run</button>
      </div>
    </div>
    <div className="card rows" style={{ padding: "8px 24px" }}>
      {list.map((r) => <div key={r.id} className="r">
        <a href="#" onClick={() => open(r.id)}><b>{r.id}</b></a>
        <span className="mut small">{r.skill} {r.baseline}→{r.candidate} ·
          {" "}model {r.model} · {r.tasks?.length || 0} tasks</span>
        <Pill v={r.status} />
        <Pill v={r.verdict || "\u2014"} />
      </div>)}
    </div>
    {det && <div className="card">
      <h3>{det.meta.id}{" "}
        {det.report && <Pill v={det.report.verdict} />}</h3>
      {det.report && <>
        <div className="small mut">
          categories: {Object.entries(det.report.counts || {})
            .filter(([, n]) => n > 0)
            .map(([k, n]) => `${k}=${n}`).join(", ") || "none"}
        </div>
        <table className="tbl mt">
          <thead><tr>{["task","kind","categories",
            "base score","cand score","base tok","cand tok",
            "base lat","cand lat"].map((h) =>
              <th key={h}>{h}</th>)}</tr></thead>
          <tbody>{det.report.tasks.map((t) => <tr key={t.task}>
            <td><b>{t.task}</b></td>
            <td>{t.kind}</td>
            <td className={t.categories.length ? "bad" : "ok"}>
              {t.categories.join(", ") || "clean"}</td>
            <td className="r">{fmt(t.baseline, "score")}</td>
            <td className="r">{fmt(t.candidate, "score")}</td>
            <td className="r">{fmt(t.baseline, "tokens")}</td>
            <td className="r">{fmt(t.candidate, "tokens")}</td>
            <td className="r">{fmt(t.baseline, "latency")}</td>
            <td className="r">{fmt(t.candidate, "latency")}</td>
          </tr>)}</tbody></table></>}
      {det.markdown && <pre className="dump">{det.markdown}</pre>}
    </div>}
  </>;
}

function Regressions() {
  return <Page title="Regressions"
    sub="controlled baseline-vs-candidate"><RegressionsBody /></Page>;
}

function ExperimentsBody() {
  const [list, setList] = useState([]);
  const [msg, setMsg] = useState("");
  const [runs, setRuns] = useState([]);
  const [cmp, setCmp] = useState({});
  const [rep, setRep] = useState({});
  const [panel, setPanel] = useState({});
  const [aux, setAux] = useState({ batch: "", model: "", limit: "",
    conclusion: "", a: "", b: "", newExp: "", newCat: "trigger" });
  const [editing, setEditing] = useState(null);   // experiment id
  const load = () => {
    api("/experiments").then(setList).catch(() => {});
    api("/runs").then(setRuns).catch(() => {});
  };
  useEffect(() => { load(); }, []);
  const run = (id) =>
    api(`/experiments/${id}/run`, { method: "POST" })
      .then((r) => { setMsg(`${id}: job ${r.job} — ` +
        `${r.planned} rollouts`); load(); })
      .catch((e) => setMsg(String(e)));
  const rerun = (id) => {
    const body = {};
    if (aux.batch) body.batch = aux.batch;
    if (aux.model) body.model = aux.model;
    if (aux.limit) body.limit = parseInt(aux.limit, 10);
    api(`/experiments/${id}/rerun`, { method: "POST",
      body: JSON.stringify(body) })
      .then((r) => { setMsg(`${id}: job ${r.job} — ` +
        `${r.planned} rollouts (batch ${r.batch || "\u2014"})`); load(); })
      .catch((e) => setMsg(String(e)));
  };
  const compare = (id) =>
    api(`/experiments/${id}/compare`)
      .then((c) => setCmp({ ...cmp, [id]: c }))
      .catch((e) => setMsg(String(e)));
  const report = (id) =>
    api(`/experiments/${id}/report`)
      .then((r) => setRep({ ...rep, [id]: r.markdown }))
      .catch((e) => setMsg(String(e)));
  const show = (id, key, p) =>
    p.then((d) => setPanel({ ...panel, [id]: { key, data: d } }))
      .catch((e) => setMsg(String(e)));
  const conclude = (id) =>
    api(`/experiments/${id}/conclude`, { method: "POST",
      body: JSON.stringify({ conclusion: aux.conclusion }) })
      .then(() => { setMsg(`${id} concluded`); load(); })
      .catch((e) => setMsg(String(e)));
  const diff = () =>
    api(`/diff/${aux.a}/${aux.b}`)
      .then((d) => setPanel({ ...panel, _diff: { key: "diff",
        data: d } }))
      .catch((e) => setMsg(String(e)));
  const create = () =>
    api("/experiments", { method: "POST",
      body: JSON.stringify({ id: aux.newExp, category: aux.newCat }) })
      .then(() => { setMsg(`created ${aux.newExp} · fill arms/tasks`);
        setAux({ ...aux, newExp: "" }); load(); })
      .catch((e) => setMsg(String(e)));
  const ax = (k) => ({ value: aux[k],
    onChange: (e) => setAux({ ...aux, [k]: e.target.value }) });
  const CATS = ["capability","trigger","workflow","instruction","resource",
    "tool-use","compatibility","reliability","efficiency"];
  return <>
    {editing && <ExperimentBuilder eid={editing}
      onClose={() => setEditing(null)}
      onRan={() => { setEditing(null); load(); }} />}
    <Msg m={msg} />
    <div className="toolbar">
      <input {...ax("newExp")} placeholder="new experiment id" />
      <select value={aux.newCat}
        onChange={(e) => setAux({ ...aux, newCat: e.target.value })}>
        {CATS.map((c) => <option key={c}>{c}</option>)}
      </select>
      <button onClick={create} disabled={!aux.newExp}>Create</button>
      <span style={{ width: 16 }} />
      <span className="mut">diff</span>
      <input {...ax("a")} placeholder="run A" style={{ width: 220 }} />
      <input {...ax("b")} placeholder="run B" style={{ width: 220 }} />
      <button onClick={diff} disabled={!aux.a || !aux.b}>
        Diff runs</button>
    </div>
    {panel._diff && <div className="card">
      <b>{panel._diff.data.run_a} vs {panel._diff.data.run_b}</b>
      <pre className="dump">{panel._diff.data.transcript_diff.join("\n")
        || "(transcripts identical)"}</pre>
      {(panel._diff.data.added.length > 0 ||
        panel._diff.data.removed.length > 0) &&
        <div className="small mono">
          {panel._diff.data.added.map((f) =>
            <div key={f} className="ok">+ {f}</div>)}
          {panel._diff.data.removed.map((f) =>
            <div key={f} className="bad">- {f}</div>)}
        </div>}
    </div>}
    {list.map((e) => <div key={e.id} className="card">
      <b>{e.id}</b> <Pill v={e.status} /> {e.title}
      <span className="pill acc" style={{ marginLeft: 6 }}>
        {e.category || "uncategorized"}</span>
      <div className="small mut">
        arms: {e.arms.map((a) => a.name + "=" + (a.skill || "none")).join(", ")}
        · tasks: {e.tasks.join(", ") || "\u2014"}
        · rollouts: {e.rollouts_per_arm}
        · model: {e.fixed ? e.fixed.model : "?"}</div>
      <div className="toolbar">
        <button className="primary" onClick={() =>
          setEditing(e.id)}>Builder</button>
        <button onClick={() => run(e.id)}>Run</button>
        <button onClick={() => compare(e.id)}>Compare</button>
        <button onClick={() => report(e.id)}>Report</button>
        <button onClick={() => show(e.id, "validate",
          api(`/experiments/${e.id}/validate`))}>Validate</button>
        <button onClick={() => show(e.id, "runs",
          api(`/experiments/${e.id}/runs`))}>Runs</button>
      </div>
      {e.status !== "concluded" && <div className="toolbar">
        <span className="mut">rerun</span>
        <input {...ax("batch")} placeholder="batch" style={{ width: 90 }} />
        <input {...ax("model")} placeholder="model" style={{ width: 110 }} />
        <input {...ax("limit")} placeholder="limit" type="number"
          style={{ width: 70 }} />
        <button onClick={() => rerun(e.id)}>Go</button>
        <span style={{ width: 10 }} />
        <input {...ax("conclusion")} placeholder="conclusion"
          style={{ width: 160 }} />
        <button onClick={() => conclude(e.id)}
          disabled={!aux.conclusion}>Conclude</button>
      </div>}
      {panel[e.id]?.key === "validate" && <div className="small mt">
        {panel[e.id].data.valid
          ? <span className="ok">valid</span>
          : panel[e.id].data.errors.map((x, i) =>
            <div key={i} className="bad">error: {x}</div>)}
        {panel[e.id].data.warnings.map((w, i) =>
          <div key={i} className="warn">warn: {w}</div>)}
      </div>}
      {panel[e.id]?.key === "runs" && <div className="rows small mt">
        {panel[e.id].data.map((x) =>
          <div key={x.run.run_id} className="r">
            <Link to={"/runs/" + x.run.run_id}>
              <code>{x.run.run_id}</code></Link>
            <Pill v={x.run.status} />
            <span className="mut">eval: {x.eval
              ? x.eval.status : "\u2014"}</span></div>)}
        {!panel[e.id].data.length &&
          <div className="r mut">no runs yet</div>}
      </div>}
      {cmp[e.id] && <table className="tbl mt">
        <thead><tr><th>arm</th>
          {cmp[e.id].tasks.map((t) => <th key={t} className="r">{t}</th>)}</tr>
        </thead>
        <tbody>{cmp[e.id].arms.map((a) => <tr key={a.name}>
          <td><b>{a.name}</b>
            <span className="mut"> {a.skill || "none"}</span></td>
          {cmp[e.id].tasks.map((t) => {
            const c = a.cells[t];
            return <td key={t} className="r">{c
              ? `${c.mean.toFixed(2)}±${c.stdev.toFixed(2)} (n=${c.n})`
              : "\u2014"}</td>;})}
        </tr>)}</tbody></table>}
      {rep[e.id] && <pre className="dump">{rep[e.id]}</pre>}
    </div>)}
    <div className="card">
      <h3>Recent runs</h3>
      <div className="rows small">{runs.slice(-10).reverse().map((r) => (
        <div key={r.run_id} className="r">
          <Link to={"/runs/" + r.run_id}><code>{r.run_id}</code></Link>
          <Pill v={r.status} />
          <span className="mut">{r.skill_ref}</span></div>))}
      </div>
    </div>
  </>;
}

function Experiments() {
  return <Page title="Experiment Lab"
    sub="arms × tasks, evidence over vibes"><ExperimentsBody /></Page>;
}

/* ---------- Benchmark module: launch + monitor + results ---------- */
function BenchLauncher({ onLaunched }) {
  const [skills, setSkills] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [f, setF] = useState({ skill: "", variant: "", tasks: [],
    rollouts: 1, model: "mock", mode: "available" });
  const [adv, setAdv] = useState(false);
  const [msg, setMsg] = useState("");
  useEffect(() => {
    api("/skills").then(setSkills).catch(() => {});
    api("/tasks").then(setTasks).catch(() => {});
    api("/status").then((s) => s?.model &&
      setF((x) => ({ ...x, model: s.model }))).catch(() => {});
  }, []);
  const sk = skills.find((s) => s.id === f.skill);
  const variants = sk?.variants || [];

  const launch = () => {
    const ref = `${f.skill}@${f.variant}`;
    const id = `bench-${f.skill}-${Date.now().toString(36)}`;
    const config = {
      id, title: `Benchmark ${ref}`,
      hypothesis: `${ref} improves task performance vs no-skill control`,
      independent_var: "skill_variant", category: "capability",
      fixed: { model: f.model || "mock", temperature: 0.0,
               seed_policy: "varied", injection_mode: f.mode,
               harness: "standard-tools-v1" },
      arms: [{ name: "control", skill: null },
             { name: "treatment", skill: ref }],
      tasks: f.tasks, rollouts_per_arm: f.rollouts,
      status: "designed",
    };
    api("/experiments", { method: "POST",
      body: JSON.stringify({ id, category: "capability", config }) })
      .then(() => api(`/experiments/${id}/run`, { method: "POST" }))
      .then((r) => { setMsg(`benchmark job ${r.job} — ` +
        `${r.planned} rollouts`); onLaunched && onLaunched(r.job); })
      .catch((e) => setMsg(String(e)));
  };
  return <div className="card">
    <h3>New benchmark <span className="mut small">
      control arm (no skill) vs treatment arm (skill)</span></h3>
    <div className="toolbar">
      <select value={f.skill} onChange={(e) => setF({ ...f,
        skill: e.target.value, variant: "" })}>
        <option value="">skill…</option>
        {skills.map((s) => <option key={s.id}>{s.id}</option>)}
      </select>
      <select value={f.variant} disabled={!f.skill}
        onChange={(e) => setF({ ...f, variant: e.target.value })}>
        <option value="">variant…</option>
        {variants.map((v) => <option key={v.id}>{v.id}</option>)}
      </select>
      <select multiple size={Math.min(4, Math.max(2, tasks.length))}
        value={f.tasks}
        onChange={(e) => setF({ ...f, tasks:
          [...e.target.selectedOptions].map((o) => o.value) })}>
        {tasks.map((t) => <option key={t.id} value={t.id}>
          {t.id} · {t.kind}</option>)}
      </select>
      <input type="number" min="1" max="10" value={f.rollouts}
        style={{ width: 70 }} title="rollouts per arm"
        onChange={(e) => setF({ ...f,
          rollouts: parseInt(e.target.value, 10) || 1 })} />
      <button className="link" onClick={() => setAdv(!adv)}>
        {adv ? "▾" : "▸"} model</button>
      <button className="primary"
        disabled={!f.skill || !f.variant || !f.tasks.length}
        onClick={launch}>Run benchmark</button>
      <span className="mut small">{msg}</span>
    </div>
    {adv && <div className="toolbar" style={{ borderTop:
      "1px solid var(--rule)", paddingTop: 10 }}>
      <label className="fld" style={{ flexDirection: "row", gap: 8,
        alignItems: "baseline" }}>model
        <input list="models" value={f.model} style={{ width: 260 }}
          onChange={(e) => setF({ ...f, model: e.target.value })} />
        <datalist id="models">
          <option value="mock" />
          <option value="anthropic/claude-sonnet-4-5" />
          <option value="anthropic/claude-haiku-4-5" />
          <option value="openai/gpt-4o" />
          <option value="openai/gpt-4o-mini" />
          <option value="gemini/gemini-2.0-flash" />
          <option value="ollama/llama3.2" />
        </datalist>
      </label>
      <label className="fld" style={{ flexDirection: "row", gap: 8,
        alignItems: "baseline" }}>mode
        <select value={f.mode}
          onChange={(e) => setF({ ...f, mode: e.target.value })}>
          <option value="available">available (trigger)</option>
          <option value="injected">injected (content)</option>
        </select>
      </label>
      {f.model === "mock" && <span className="pill warn">simulated</span>}
    </div>}
  </div>;
}

function JobsCard({ jobs }) {
  const act = (jobs || []).filter((j) =>
    ["queued", "running"].includes(j.status));
  if (!act.length) return null;
  return <div className="card">
    <h3>Running jobs</h3>
    {act.map((j) => <div key={j.id} className="r small">
      <code>{j.id}</code> <Pill v={j.status} />
      <span className="mut">{j.operation || j.kind}</span>
      <div className="prog" style={{ flex: 1, minWidth: 80 }}>
        <div className="prog-bar"
          style={{ width: `${(j.progress || 0) * 100}%` }} /></div>
    </div>)}
  </div>;
}

function Benchmarks() {
  const [jobs, setJobs] = useState([]);
  useEffect(() => {
    const poll = () => api("/jobs").then(setJobs).catch(() => {});
    poll();
    const t = setInterval(poll, 2000);
    return () => clearInterval(t);
  }, []);
  return <Page title="Benchmark"
    sub="controlled evidence — baseline vs skill, version vs version">
    <BenchLauncher />
    <JobsCard jobs={jobs} />
    <ExperimentsBody />
    <RegressionsBody />
  </Page>;
}

/* ---------- Report module: quality report per skill variant ------- */
function Report() {
  const [skills, setSkills] = useState([]);
  const [ref, setRef] = useState("");
  const [rep, setRep] = useState(null);
  const [msg, setMsg] = useState("");
  useEffect(() => { api("/skills").then(setSkills).catch(() => {}); },
    []);
  const refs = [];
  skills.forEach((s) => (s.variants || []).forEach((v) =>
    refs.push(`${s.id}@${v.id}`)));
  const load = (r) => {
    const [s, v] = r.split("@");
    api(`/report/${s}/${v}`).then(setRep)
      .catch((e) => { setRep(null); setMsg(String(e)); });
  };
  const exportMd = () => {
    const [s, v] = ref.split("@");
    fetch(`/api/v1/report/${s}/${v}?format=md`,
      { headers: { Authorization: `Bearer ${tok()}` } })
      .then((r) => r.blob())
      .then((b) => {
        const a = document.createElement("a");
        a.href = URL.createObjectURL(b);
        a.download = `${s}-${v}-report.md`; a.click();
        URL.revokeObjectURL(a.href); });
  };
  return <Page title="Quality Report"
    sub="evidence-based summary for agency clients">
    <div className="toolbar">
      <select value={ref} onChange={(e) => { setRef(e.target.value);
        setRep(null); setMsg(""); if (e.target.value)
        load(e.target.value); }}>
        <option value="">select skill@variant…</option>
        {refs.map((r) => <option key={r}>{r}</option>)}
      </select>
      {rep && <button className="primary" onClick={exportMd}>
        Export .md</button>}
      <span className="mut small">{msg}</span>
    </div>
    {!ref && <div className="card empty mut">
      Pick a skill version to build its quality report — benchmarks,
      regression suites and the release checklist are assembled into a
      single client-facing summary.</div>}
    {rep && <>
      <div className="card">
        <h3>{rep.skill}@{rep.variant} {" "}
          <span className={"pill " + (rep.verdict.label === "improved"
            || rep.verdict.label === "validated" ? "pos"
            : rep.verdict.label === "regressed"
            || rep.verdict.label === "degraded" ? "neg" : "warn")}>
            {rep.verdict.label}</span></h3>
        <div className="small">{rep.verdict.text}</div>
        <div className="small mut mono">hash {rep.content_hash}
          {" · "}{rep.generated}{rep.simulated &&
            " · simulated (model: mock)"}</div>
      </div>
      {rep.experiments.length > 0 && <div className="card">
        <h3>Benchmarks ({rep.experiments.length})</h3>
        {rep.experiments.map((e) => <div key={e.experiment}
          className="r small">
          <code>{e.experiment}</code>
          <span className="mut">{e.model} · {e.injection_mode}</span>
          {Object.entries(e.arms).map(([an, a]) =>
            <span key={an}>{an}{a.skill ? ` (${a.skill})` : " (ctrl)"}:
              {" "}{a.mean.toFixed(3)} <span className="mut">n={a.n}</span>
            </span>)}
          {"delta_vs_control" in e &&
            <b className={e.delta_vs_control > 0 ? "ok" : "bad"}>
              Δ {e.delta_vs_control > 0 ? "+" : ""}
              {e.delta_vs_control}</b>}
        </div>)}
      </div>}
      {rep.regressions.length > 0 && <div className="card">
        <h3>Regression suites ({rep.regressions.length})</h3>
        {rep.regressions.map((r) => <div key={r.id} className="r small">
          <code>{r.id}</code>
          <span className="mut">{r.baseline} → {r.candidate}</span>
          <Pill v={(r.report || {}).verdict || r.verdict || "running"} />
        </div>)}
      </div>}
      {rep.releases.length > 0 && <div className="card">
        <h3>Release checklist</h3>
        {rep.releases.map((r) => <div key={r.version}>
          <b>v{r.version}</b> <Pill v={r.status} />
          <div className="small mono" style={{ marginTop: 6 }}>
            {(r.checklist || []).map((c) =>
              <div key={c.id} className={c.ok ? "ok" : "bad"}>
                {c.ok ? "✓" : "✗"} {c.id} — {c.detail}</div>)}
          </div></div>)}
      </div>}
    </>}
  </Page>;
}

function Workspace() {
  const [ts, setTs] = useState([]);
  const [rb, setRb] = useState([]);
  const [msg, setMsg] = useState("");
  const load = () => {
    api("/tasks").then(setTs).catch(() => {});
    api("/rubrics").then(setRb).catch(() => {});
  };
  useEffect(() => { load(); }, []);
  const mk = (kind) => (v) =>
    api(`/${kind}`, { method: "POST", body: JSON.stringify({ id: v }) })
      .then(() => { setMsg(`${kind} '${v}' scaffolded`); load(); })
      .catch((e) => setMsg(String(e)));
  return <Page title="Test Suite" sub="tasks the agent is scored on + rubric criteria">
    <Msg m={msg} />
    <div className="card">
      <h3>Tasks ({ts.length})</h3>
      <AddForm ph="new task id" onAdd={mk("tasks")} />
      <div className="rows">{ts.map((t) => <div key={t.id}
        className="r" style={{ alignItems: "baseline" }}>
        <div style={{ flex: 1 }}>
          <b>{t.id}</b> <span className="pill acc">{t.kind}</span>
          <span className="mut small"> rubric: {t.rubric || "\u2014"} · checks:
            {" "}{(t.deterministic_checks || []).length} · fixtures:
            {" "}{(t.fixtures || []).join(", ") || "\u2014"}</span>
          {t.skill_relevance && (t.skill_relevance.expected?.length ||
            t.skill_relevance.unexpected?.length) > 0 &&
            <div className="small" style={{ color: "var(--accent)" }}>
              expect: {(t.skill_relevance.expected || []).join(", ") ||
                "\u2014"} · not: {(t.skill_relevance.unexpected || [])
                .join(", ") || "\u2014"}</div>}
          <div className="small mut">
            {(t.prompt || "").trim().slice(0, 140)}</div>
        </div>
      </div>)}</div>
    </div>
    <div className="card">
      <h3>Rubrics ({rb.length})</h3>
      <AddForm ph="new rubric id" onAdd={mk("rubrics")} />
      {rb.map((r) => <div key={r.id} className="mt">
        <b>{r.id}</b>
        <table className="tbl">
          <tbody>{(r.criteria || []).map((c, i) => <tr key={i}>
            <td>{c.id}</td>
            <td className="num">w={c.weight}</td>
            <td>{c.method}</td>
            <td className="mut">{c.check || c.scale || ""}</td>
          </tr>)}</tbody></table>
      </div>)}
    </div>
  </Page>;
}

function RunDetail() {
  const { rid } = useParams();
  const [d, setD] = useState(null);
  const [art, setArt] = useState(null);
  const [scores, setScores] = useState({});
  const [msg, setMsg] = useState("");
  const [showTr, setShowTr] = useState(false);
  const load = () => api("/runs/" + rid).then(setD)
    .catch((e) => setMsg(String(e)));
  useEffect(() => { load(); }, [rid]);
  useEffect(() => { setArt(null); setScores({}); setMsg(""); }, [rid]);
  if (!d) return <Page title="Run">
    <Msg m={msg} />{!msg && <p className="mut">loading…</p>}</Page>;
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
    ["eval", ev ? ev.status : "\u2014"],
    ["score", ev && ev.rubric_score != null
      ? ev.rubric_score.toFixed(2) : "\u2014"],
    ["turns", r.usage?.turns],
    ["tokens", (r.usage?.input_tokens || 0) + (r.usage?.output_tokens || 0)]];
  return <Page title={r.run_id}
    sub={`experiment ${r.experiment} · arm ${r.arm} · task ${r.task} · ` +
      `model ${r.model?.name} · mode ${r.injection_mode} · ` +
      `skill ${r.skill_ref || "none"}`}>
    <Msg m={msg} />
    {r.error && <Msg m={"run error: " + r.error} />}
    <div className="kpis">
      {stats.map(([k, v]) => <div key={k}>
        <div className="k">{k}</div>
        <div className="v">{v ?? "\u2014"}</div></div>)}
    </div>
    <div className="card">
      <h3>Evaluation {ev && <Pill v={ev.status} />}</h3>
      {ev ? <>
        <table className="tbl">
          <thead><tr>{["criterion","method","status","score","judge",
            "detail"].map((h) => <th key={h}>{h}</th>)}</tr></thead>
          <tbody>{ev.checks.map((c) => <tr key={c.id}>
            <td><b>{c.id}</b></td>
            <td>{c.method}</td>
            <td><Pill v={c.status} /></td>
            <td className="r num">
              {c.score != null ? c.score.toFixed(2) : "\u2014"}</td>
            <td className="mut">{c.judge_model || "\u2014"}</td>
            <td className="mut">{(c.detail || "").slice(0, 120)}</td>
          </tr>)}</tbody></table>
        <div className="toolbar">
          <button onClick={reeval}>Re-evaluate</button>
          {ev.evaluated_at && <span className="mut small">
            evaluated at {ev.evaluated_at}</span>}
        </div>
        {humanPending.length > 0 && <div className="panel">
          <b>Human scoring</b>
          {humanPending.map((c) => <div key={c.id} className="toolbar">
            <label className="small">{c.id}: </label>
            <input type="number" step="0.5" min="0" style={{ width: 70 }}
              value={scores[c.id] ?? ""}
              onChange={(e) => setScores({ ...scores,
                [c.id]: parseFloat(e.target.value) })} />
          </div>)}
          <button onClick={score}
            disabled={!Object.keys(scores).length}>Apply scores</button>
        </div>}
      </> : <p className="bad small">
        no eval.yaml · evaluation missing or pending{" "}
        <button onClick={reeval}>Evaluate</button></p>}
    </div>
    {failure && <div className="card">
      <h3>Failure analysis <Pill v={failure.verdict} /></h3>
      <table className="tbl">
        <thead><tr>{["category","hypothesis","evidence"].map((h) =>
          <th key={h}>{h}</th>)}</tr></thead>
        <tbody>{(failure.causes || []).map((c, i) => <tr key={i}>
          <td className="bad">{c.category}</td>
          <td>{(c.hypothesis || "").slice(0, 110)}</td>
          <td className="mut">{(c.evidence || "").slice(0, 80)}</td>
        </tr>)}</tbody></table>
    </div>}
    {r.skill_events?.length > 0 && <div className="card">
      <h3>Skill events</h3>
      <table className="tbl">
        <thead><tr>{["turn","event","skill","path"].map((h) =>
          <th key={h}>{h}</th>)}</tr></thead>
        <tbody>{r.skill_events.map((e, i) => <tr key={i}>
          <td className="num">{e.t}</td><td>{e.event}</td>
          <td>{e.skill || "\u2014"}</td>
          <td className="mut">{e.path || "\u2014"}</td>
        </tr>)}</tbody></table>
    </div>}
    {artifacts?.length > 0 && <div className="card">
      <h3>Artifacts ({artifacts.length})</h3>
      <div className="rows small">{artifacts.map((p) =>
        <div key={p} className="r">
          <a href="#" onClick={() => openArt(p)}><code>{p}</code></a>
        </div>)}</div>
      {art && <pre className="dump">
        <b>{art.path}</b>{"\n"}{art.text.slice(0, 8000)}</pre>}
    </div>}
    <div className="card">
      <h3><a href="#" onClick={() => setShowTr(!showTr)}
        style={{ color: "inherit" }}>Transcript {showTr ? "▾" : "▸"}
        {transcript ? ` (${transcript.length})` : ""}</a></h3>
      {showTr && (transcript || []).map((m, i) => (
        <div key={i} style={{ fontSize: 12, margin: "6px 0",
          borderLeft: "2px solid var(--control)", paddingLeft: 10 }}>
          <b style={{ color: m.role === "assistant"
            ? "var(--accent)" : "var(--muted)" }}>
            #{i} {m.role}{m.name ? ` [${m.name}]` : ""}</b>
          {m.usage && <span className="mut num" style={{ fontSize: 10,
            marginLeft: 8 }}>in={m.usage.input} out={m.usage.output}</span>}
          {m.role === "assistant" && m.tool_calls
            ? m.tool_calls.map((tc, j) => <div key={j}>
                <b className="ok">→ {tc.function?.name || "?"}</b>
                <pre className="dump" style={{ marginTop: 2 }}>
                  {(tc.function?.arguments || "").slice(0, 600)}</pre></div>)
            : <pre className="dump" style={{ marginTop: 2 }}>
                {(m.content || "").slice(0, 3000)}</pre>}
        </div>))}
      {showTr && d.transcript_truncated &&
        <p className="warn small">transcript truncated</p>}
    </div>
  </Page>;
}

function Blueprints() {
  const [projects, setProjects] = useState([]);
  const [sel, setSel] = useState(null);
  const [bpPid, setBpPid] = useState("");
  const [proj, setProj] = useState(null);
  const [msg, setMsg] = useState("");
  const [newBp, setNewBp] = useState("");
  useEffect(() => { api("/projects").then(setProjects).catch(() => {}); }, []);
  const pick = (pid) => { setBpPid(pid);
    api(`/projects/${pid}/blueprints`).then(setSel).catch(() => setSel([]));
    api(`/projects/${pid}`).then(setProj).catch(() => setProj(null)); };
  const create = () =>
    api(`/projects/${bpPid}/blueprints`,
        { method: "POST", body: JSON.stringify({ id: newBp,
          title: newBp }) })
      .then(() => { setNewBp(""); pick(bpPid); })
      .catch((e) => setMsg(String(e)));
  return <Page title="Blueprints" sub="research → SKILL.md contract">
    <Msg m={msg} />
    <div className="toolbar">
      {projects.map((p) => (
        <button key={p.id} onClick={() => pick(p.id)}>{p.id}</button>))}
    </div>
    {bpPid && <div className="toolbar">
      <input value={newBp} placeholder="new blueprint id"
        onChange={(e) => setNewBp(e.target.value)} />
      <button onClick={create} disabled={!newBp}>Create</button></div>}
    {sel && sel.map((b) => <div key={b.id} className="card">
      <b>{b.id}</b> <Pill v={b.status} />
      <span className="mut small"> rev {b.rev}</span> · {b.title}
      <div className="small mut">
        findings: {(b.related_findings || []).join(", ") || "\u2014"} ·
        generated: {(b.generated_variants || []).join(", ") || "\u2014"}</div>
      <BpActions pid={bpPid} b={b} proj={proj}
        reload={() => pick(bpPid)} onErr={setMsg} />
      <b>Fields</b>
      <ul>
        {Object.entries(b.fields || {}).filter(([, v]) =>
          v && (Array.isArray(v) ? v.length : true))
          .map(([k, v]) => <li key={k}><b>{k}</b>: {String(v).slice(0, 90)}
            </li>)}
      </ul>
      <BpEdit pid={bpPid} bid={b.id} fields={b.fields}
        reload={() => pick(bpPid)} /></div>)}
    {sel && sel.length === 0 && <p className="mut">
      no blueprints in this project</p>}
  </Page>;
}

function BpActions({ pid, b, proj, reload, onErr }) {
  const [panel, setPanel] = useState("");
  const [data, setData] = useState(null);
  const [aux, setAux] = useState({ finding: "", qid: "", skill: "",
    variant: "", format: "skill-md", force: false, ref: "",
    exp_id: "", from_rev: "" });
  const post = (url, body, ok) =>
    api(url, { method: "POST", body: JSON.stringify(body || {}) })
      .then((r) => { ok ? ok(r) : reload(); })
      .catch((e) => onErr(String(e)));
  const get = (url, key) =>
    api(url).then((r) => { setPanel(key); setData(r); })
      .catch((e) => onErr(String(e)));
  const B = `/projects/${pid}/blueprints/${b.id}`;
  return <div className="small mt">
    <div className="toolbar">
      <StatusSel value={b.status}
        options={["draft","designing","ready_for_generation","generated",
          "testing","improving","validated","released","archived"]}
        onChange={(s) => post(`${B}/status`, { status: s })} />
      <button onClick={() => get(`${B}/validate`, "validate")}>
        Validate</button>
      <button onClick={() =>
        post(`${B}/draft`, {}, (r) => { setPanel("draft"); setData(r); })}>
        Draft from research</button>
      <button onClick={() => get(`${B}/revisions`, "revs")}>
        Revisions</button>
    </div>
    <div className="toolbar">
      {proj && <>
        <select value={aux.qid}
          onChange={(e) => setAux({ ...aux, qid: e.target.value })}>
          <option value="">question…</option>
          {proj.questions.map((q) =>
            <option key={q.id} value={q.id}>{q.id}</option>)}
        </select>
        <button disabled={!aux.qid}
          onClick={() => post(`${B}/from-question`, { qid: aux.qid })}>
          Prefill</button>
        <select value={aux.finding}
          onChange={(e) => setAux({ ...aux, finding: e.target.value })}>
          <option value="">finding…</option>
          {proj.findings.map((f) =>
            <option key={f.id} value={f.id}>{f.id}</option>)}
        </select>
        <button disabled={!aux.finding}
          onClick={() => post(`${B}/link`, { finding: aux.finding })}>
          Link</button>
      </>}
    </div>
    <div className="toolbar">
      <span className="mut">generate</span>
      <input value={aux.skill} placeholder="skill" style={{ width: 110 }}
        onChange={(e) => setAux({ ...aux, skill: e.target.value })} />
      <input value={aux.variant} placeholder="variant" style={{ width: 80 }}
        onChange={(e) => setAux({ ...aux, variant: e.target.value })} />
      <select value={aux.format}
        onChange={(e) => setAux({ ...aux, format: e.target.value })}>
        <option value="skill-md">skill-md</option>
        <option value="system-prompt">system-prompt</option>
      </select>
      <label className="small"><input type="checkbox"
        checked={aux.force}
        onChange={(e) => setAux({ ...aux, force: e.target.checked })} />
        force</label>
      <button disabled={!aux.skill || !aux.variant}
        onClick={() => post(`${B}/generate`,
          { skill: aux.skill, variant: aux.variant,
            format: aux.format, force: aux.force })}>Generate</button>
    </div>
    <div className="toolbar">
      <span className="mut">scaffold</span>
      <input value={aux.exp_id} placeholder="exp id (opt)"
        style={{ width: 110 }}
        onChange={(e) => setAux({ ...aux, exp_id: e.target.value })} />
      <button disabled={!aux.skill || !aux.variant}
        onClick={() => post(`${B}/experiment`,
          { skill: aux.skill, variant: aux.variant,
            exp_id: aux.exp_id || null },
          (r) => { setPanel("exp"); setData(r); })}>Experiment</button>
      <span className="mut">drift</span>
      <input value={aux.ref} placeholder="skill@variant"
        style={{ width: 150 }}
        onChange={(e) => setAux({ ...aux, ref: e.target.value })} />
      <button disabled={!aux.ref}
        onClick={() => get(`${B}/drift?ref=${encodeURIComponent(aux.ref)}`,
          "drift")}>Check drift</button>
      <span className="mut">diff</span>
      <input value={aux.from_rev} placeholder="from rev" type="number"
        style={{ width: 70 }}
        onChange={(e) => setAux({ ...aux, from_rev: e.target.value })} />
      <button disabled={!aux.from_rev}
        onClick={() => get(`${B}/diff?from_rev=${aux.from_rev}`,
          "diff")}>Diff→now</button>
    </div>
    {panel === "validate" && data && <table className="tbl">
      <tbody>{data.map((i, k) => <tr key={k}>
        <td className={i.severity === "error" ? "bad" : "warn"}>
          {i.severity}</td>
        <td>{i.check}</td>
        <td>{i.field || ""}</td>
        <td>{i.message}</td></tr>)}
      {!data.length && <tr><td>no issues</td></tr>}
      </tbody></table>}
    {panel === "draft" && data && <div className="small ok mt">
      touched: {data.touched.join(", ") || "none"}
    </div>}
    {panel === "exp" && data && <div className="small ok mt">
      experiment {data.experiment} · created:
      {" "}{data.tasks_created.join(", ") || "\u2014"}; skipped:
      {" "}{data.tasks_skipped.join(", ") || "\u2014"}</div>}
    {panel === "revs" && data && <ul>
      {data.map((r) => <li key={r.rev}>r{r.rev} [{r.status}]
        {" "}{r.updated}</li>)}</ul>}
    {panel === "diff" && data && <ul>
      {(data.diffs || []).map((d, k) => <li key={k}>
        <b>{d.field}</b>: {String(d.from).slice(0, 50)} →
        {" "}{String(d.to).slice(0, 50)}</li>)}
      {!data.diffs?.length && <li>no field changes</li>}</ul>}
    {panel === "drift" && data && <div className="small mt">
      <b className={data.status === "synced" ? "ok" : "bad"}>
        {data.status}</b>
      {" "}gen@r{data.gen_rev ?? "?"} vs bp r{data.bp_rev}
      {data.diff && <pre className="dump">
        {data.diff.slice(0, 3000)}</pre>}
    </div>}
  </div>;
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
  const exec = async () => {
    // authenticated SSE via fetch streaming — EventSource can't send
    // the bearer header, and tokens never go in query strings
    const ac = new AbortController();
    try {
      await api(`/research/${pid}/${run.id}/run`, { method: "POST" });
      const res = await fetch(
        `/api/v1/research/${pid}/${run.id}/stream`,
        { headers: { Authorization: `Bearer ${tok()}` },
          signal: ac.signal });
      if (!res.ok || !res.body) { setErr(`stream ${res.status}`); return; }
      const reader = res.body.getReader();
      const dec = new TextDecoder();
      let buf = "";
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        let i;
        while ((i = buf.indexOf("\n\n")) >= 0) {
          const chunk = buf.slice(0, i); buf = buf.slice(i + 2);
          const line = chunk.split("\n")
            .find((l) => l.startsWith("data: "));
          if (!line) continue;
          const s = JSON.parse(line.slice(6));
          setRun((r) => ({ ...r,
            state: { ...(r.state || {}), ...s } }));
          if (["completed", "failed"].includes(s.status)) {
            ac.abort(); return;
          }
        }
      }
    } catch (e) {
      if (e.name !== "AbortError") setErr(`stream lost: ${e}`);
    }
  };
  const show = () =>
    api(`/research/${pid}/${run.id}`).then((s) =>
      setRun({ ...run, state: s })).catch(() => {});
  const st = run && run.state ? run.state : null;
  return <Page title="Deep Research" sub="planned multi-query sweep">
    <div className="toolbar">
      <select value={pid} onChange={(e) => setPid(e.target.value)}>
        <option value="">project…</option>
        {projects.map((p) => <option key={p.id} value={p.id}>{p.id}</option>)}
      </select>
      <input value={obj} onChange={(e) => setObj(e.target.value)}
        placeholder="research objective" style={{ width: 420 }} />
      <button className="primary" onClick={start} disabled={!pid || !obj}>
        Plan</button>
    </div>
    <Msg m={err} />
    {st && <div className="card">
      <code><b>{run.id}</b></code> <Pill v={st.status} />
      <span className="mut small"> model: {st.model}</span>
      <div className="small mt">queries: {(st.plan?.queries || [])
        .join(" · ")}</div>
      {st.status !== "completed" && <div className="toolbar">
        <button className="primary" onClick={exec}>Run (bounded)</button>
        <button onClick={show}>Refresh</button></div>}
      {st.report_md && <pre className="dump"
        style={{ maxHeight: 500 }}>{st.report_md}</pre>}
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
        <label className="small mut">{k}</label><br/>
        {isList
          ? <textarea rows={3} value={cur} style={{ width: "100%" }}
              onChange={(e) => setVals({ ...vals,
                [k]: e.target.value.split("\n").filter(Boolean) })} />
          : <input value={cur} style={{ width: "100%" }}
              onChange={(e) => setVals({ ...vals, [k]: e.target.value })} />}
      </div>;})}
    <button onClick={save} disabled={!Object.keys(vals).length}>
      Save changes</button>
    {msg && <span className="ok small" style={{ marginLeft: 8 }}>{msg}</span>}
  </div>;
}

function Gate() {
  /* Sign-in screen: without a token every api() call would 401 —
     gate first so pages never fire doomed requests. Saving a valid
     token fires the "storage" event that flips App into the shell. */
  const [tk, setTk] = useState("");
  const [err, setErr] = useState("");
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
  return (
    <div className="gate">
      <div className="gate-card">
        <div className="gate-logo">skill<span>lab</span></div>
        <div className="small mut">api token</div>
        <input autoFocus value={tk} placeholder="SKILLLAB_TOKEN"
          onChange={(e) => setTk(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && tryToken()} />
        {err && <div className="small" style={{ color:
          "var(--pill-negative-ink)" }}>{err}</div>}
        <button className="primary" onClick={tryToken}>Sign in</button>
      </div>
    </div>);
}

export default function App() {
  const [authed, setAuthed] = useState(!!tok());
  useEffect(() => {
    const f = () => setAuthed(!!tok());
    window.addEventListener("storage", f);
    return () => window.removeEventListener("storage", f);
  }, []);
  if (!authed) return <Gate />;
  return (<div className="shell"><Rail /><Routes>
    <Route path="/" element={<Home />} />
    <Route path="/benchmark" element={<Benchmarks />} />
    <Route path="/report" element={<Report />} />
    <Route path="/suite" element={<Workspace />} />
    <Route path="/projects" element={<Projects />} />
    <Route path="/explorer" element={<Explorer />} />
    <Route path="/deep" element={<DeepResearch />} />
    <Route path="/skills" element={<Skills />} />
    <Route path="/blueprints" element={<Blueprints />} />
    <Route path="/experiments" element={<Experiments />} />
    <Route path="/runs/:rid" element={<RunDetail />} />
    <Route path="/regressions" element={<Regressions />} />
    <Route path="/workspace" element={<Workspace />} />
    <Route path="/proposals" element={<Proposals />} />
    <Route path="/failures" element={<Failures />} />
    <Route path="/knowledge" element={<Knowledge />} />
    <Route path="/releases" element={<Releases />} />
  </Routes></div>);
}
