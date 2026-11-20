import React, { useEffect, useState } from "react";
import { Link, NavLink, Route, Routes } from "react-router-dom";

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
                 ["/explorer", "Web Explorer"], ["/skills", "Skill Studio"],
                 ["/proposals", "AI Architect"], ["/failures", "Failures"], ["/releases", "Releases"]];
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
      <b>Findings</b>
      <ul>{sel.findings.map((f) => (
        <li key={f.id}>{f.id} [{f.status}/{f.confidence}] {f.statement}</li>))}
      </ul></div>}
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
    <Route path="/skills" element={<Skills />} />
    <Route path="/proposals" element={<Proposals />} />
    <Route path="/failures" element={<Failures />} />
    <Route path="/releases" element={<Releases />} />
  </Routes></>);
}
