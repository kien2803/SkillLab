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
                 ["/blueprints", "Blueprints"], ["/experiments", "Experiments"], ["/regressions", "Regressions"],
                 ["/proposals", "AI Architect"], ["/failures", "Failures"], ["/knowledge", "Knowledge"], ["/releases", "Releases"]];
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
  const [st, setSt] = useState(null);
  const [sh, setSh] = useState({ name: "", tasks: false, src: "",
    force: false, msg: "" });
  useEffect(() => {
    Promise.all([api("/projects"), api("/skills"), api("/experiments"),
                 api("/releases"), api("/status")])
      .then(([projects, skills, experiments, releases, status]) => {
        setData({ projects, skills, experiments, releases });
        setSt(status); })
      .catch(() => setData({}));
  }, []);
  const cards = [["projects", data.projects], ["skills", data.skills],
                 ["experiments", data.experiments],
                 ["releases", data.releases]];
  const post = (url, body) =>
    api(url, { method: "POST", body: JSON.stringify(body) })
      .then((r) => setSh({ ...sh, msg:
        r.path ? `→ ${r.path}`
               : `imported ${r.imported ?? 0}, skipped ` +
                 `${r.skipped ?? 0}, rejected ${r.rejected ?? 0}` }))
      .catch((e) => setSh({ ...sh, msg: String(e) }));
  return <Page>
    {st && <div style={{ ...card, fontSize: 12 }}>
      <b>lab:</b> {st.root} · <b>model:</b> {st.model}
      {" "}(judge: {st.judge_model}) · <b>sandbox:</b>
      {" "}{st.sandbox || "off"} · <b>runs:</b> {st.runs}
      <span style={{ color: "#888" }}> · files:{" "}
        {Object.entries(st.counts || {}).map(([k, n]) =>
          `${k}=${n}`).join(" ")}</span>
      {(st.warnings || []).map((w, i) =>
        <div key={i} style={{ color: "#aa5" }}>warn: {w}</div>)}
      <div style={{ marginTop: 6, borderTop: "1px solid #222",
        paddingTop: 6 }}>
        share pack:
        <input value={sh.name} placeholder="export name" style={inp}
          onChange={(e) => setSh({ ...sh, name: e.target.value })} />
        <label style={{ fontSize: 11 }}>
          <input type="checkbox" checked={sh.tasks}
            onChange={(e) => setSh({ ...sh, tasks: e.target.checked })} />
          +tasks</label>
        <button disabled={!sh.name} onClick={() =>
          post("/export", { name: sh.name, tasks: sh.tasks })}>
          Export</button>
        <input value={sh.src} placeholder="import from pack dir"
          style={{ ...inp, width: 240, marginLeft: 12 }}
          onChange={(e) => setSh({ ...sh, src: e.target.value })} />
        <label style={{ fontSize: 11 }}>
          <input type="checkbox" checked={sh.force}
            onChange={(e) => setSh({ ...sh, force: e.target.checked })} />
          force</label>
        <button disabled={!sh.src} onClick={() =>
          post("/import", { src: sh.src, force: sh.force })}>
          Import</button>
        {sh.msg && <span style={{ color: "#8f8", marginLeft: 8 }}>
          {sh.msg}</span>}
      </div>
    </div>}
    <div style={{ display: "grid", gap: 12,
                  gridTemplateColumns: "repeat(4,1fr)" }}>
      {cards.map(([k, v]) => (
        <div key={k} style={card}>
          <div style={{ fontSize: 28 }}>{v ? v.length : "—"}</div>
          <div style={{ color: "#888" }}>{k}</div></div>))}
    </div></Page>;
}

function StatusSel({ value, options, onChange }) {
  return <select value={value}
    onChange={(e) => onChange(e.target.value)}
    style={{ background: "#0a0c0f", color: "#ddd",
             border: "1px solid #333", fontSize: 11 }}>
    {options.map((o) => <option key={o} value={o}>{o}</option>)}
  </select>;
}

function Projects() {
  const [list, setList] = useState([]);
  const [sel, setSel] = useState(null);
  const [msg, setMsg] = useState("");
  const [newP, setNewP] = useState("");
  const [link, setLink] = useState({ qid: "", field: "findings",
    ref: "" });
  const load = () => api("/projects").then(setList).catch(() => {});
  useEffect(load, []);
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
  return <Page><h2>Research Projects</h2>
    {msg && <p style={{ color: "#f88" }}>{msg}</p>}
    <AddForm ph="new project id" onAdd={(v) =>
      api("/projects", { method: "POST",
        body: JSON.stringify({ id: v, title: v }) })
        .then(load).catch((e) => setMsg(String(e)))} />
    {list.map((p) => (
      <div key={p.id} style={card}>
        <Link to={"#"} onClick={() => reload(p.id)}>{p.id}</Link>
        <span style={{ color: "#888" }}> — {p.title} [{p.status}]</span>
        <span style={{ marginLeft: 8 }}>
          <StatusSel value={p.status}
            options={["draft","active","researching","designing",
              "developing","experimenting","validating","completed",
              "archived"]}
            onChange={(s) => pstat(p.id, s)} />
          {p.status === "draft" &&
            <button style={{ marginLeft: 6 }}
              onClick={() => del(p.id)}>delete</button>}
        </span>
      </div>))}
    {sel && <div style={card}>
      <h3>{sel.meta.title || sel.meta.id}
        <span style={{ color: "#888", fontSize: 12 }}>
          {" "}[{sel.meta.status}]</span></h3>
      <p style={{ fontSize: 12 }}>{sel.meta.objective}</p>
      <b>Questions ({sel.questions.length})</b>
      <ul style={{ fontSize: 12 }}>{sel.questions.map((q) => (
        <li key={q.id}>{q.id} {q.question}
          <StatusSel value={q.status}
            options={["open","investigating","answered","deferred"]}
            onChange={(s) => post(
              `/projects/${sel.meta.id}/questions/${q.id}/status`,
              { status: s })} />
          {(q.findings.length + q.experiments.length) > 0 &&
            <span style={{ color: "#888" }}> →
              {" "}{q.findings.concat(q.experiments).join(", ")}</span>}
        </li>))}</ul>
      <AddForm ph="new question" onAdd={(v) =>
        post(`/projects/${sel.meta.id}/questions`, { text: v })} />
      <div style={{ fontSize: 12, margin: "4px 0" }}>
        link: <select value={link.qid}
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
        <input value={link.ref} placeholder="ref id"
          style={{ ...inp, width: 160 }}
          onChange={(e) => setLink({ ...link, ref: e.target.value })} />
        <button disabled={!link.qid || !link.ref}
          onClick={() => post(
            `/projects/${sel.meta.id}/questions/${link.qid}/link`,
            link)}>Link</button>
      </div>
      <b>Findings ({sel.findings.length})</b>
      <ul style={{ fontSize: 12 }}>{sel.findings.map((f) => (
        <li key={f.id}>{f.id} [{f.kind}/{f.confidence}] {f.statement}
          <StatusSel value={f.status}
            options={["candidate","supported","refuted","inconclusive"]}
            onChange={(s) => post(
              `/projects/${sel.meta.id}/findings/${f.id}/status`,
              { status: s })} />
        </li>))}</ul>
      <AddForm ph="new finding" onAdd={(v) =>
        post(`/projects/${sel.meta.id}/findings`, { statement: v })} />
      <b>Sources ({sel.sources.length})</b>
      <ul style={{ fontSize: 12 }}>{sel.sources.map((s) => (
        <li key={s.id}>{s.id} [{s.type}] {s.title}
          {s.url && <span style={{ color: "#888" }}> — {s.url}</span>}
          {s.annotations.map((a, i) =>
            <div key={i} style={{ color: "#ad7" }}>note: {a}</div>)}
        </li>))}</ul>
      <SrcForm pid={sel.meta.id} onDone={() => reload(sel.meta.id)}
        onErr={setMsg} />
      <b>Decisions ({sel.decisions.length})</b>
      <ul style={{ fontSize: 12 }}>{sel.decisions.map((d) => (
        <li key={d.id}>{d.id} {d.decision}
          <StatusSel value={d.status}
            options={["proposed","accepted","rejected","superseded"]}
            onChange={(s) => post(
              `/projects/${sel.meta.id}/decisions/${d.id}/status`,
              { status: s })} />
          {d.rationale && <div style={{ color: "#888" }}>
            {d.rationale}</div>}
        </li>))}</ul>
      <AddForm ph="new decision" onAdd={(v) =>
        post(`/projects/${sel.meta.id}/decisions`, { decision: v })} />
      <b>Notes ({sel.notes.length})</b>
      <ul style={{ fontSize: 12 }}>{sel.notes.map((n) => (
        <li key={n.id}>{n.id} <span style={{ color: "#888" }}>
          {n.created}</span></li>))}</ul>
      <AddForm ph="new note title" onAdd={(v) =>
        post(`/projects/${sel.meta.id}/notes`, { title: v })} />
      </div>}
  </Page>;
}

function SrcForm({ pid, onDone, onErr }) {
  const [f, setF] = useState({ type: "note", title: "", url: "",
    author: "" });
  return <div style={{ fontSize: 12, margin: "4px 0" }}>
    <select value={f.type}
      onChange={(e) => setF({ ...f, type: e.target.value })}>
      {["url","doc","note","paper","other"].map((t) =>
        <option key={t} value={t}>{t}</option>)}
    </select>
    <input value={f.title} placeholder="title" style={{ ...inp,
      width: 200 }}
      onChange={(e) => setF({ ...f, title: e.target.value })} />
    {f.type === "url" &&
      <input value={f.url} placeholder="url" style={{ ...inp,
        width: 200 }}
        onChange={(e) => setF({ ...f, url: e.target.value })} />}
    <input value={f.author} placeholder="author" style={{ ...inp,
      width: 120 }}
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
  const [panel, setPanel] = useState(null);   // {kind, data}
  const [msg, setMsg] = useState("");
  const [newSk, setNewSk] = useState("");
  const [imp, setImp] = useState("");
  const load = () => api("/skills").then(setList).catch(() => {});
  useEffect(load, []);
  const show = (kind, p) =>
    p.then((d) => setPanel({ kind, data: d }))
      .catch((e) => setMsg(String(e)));
  const suggest = (ref, llm) =>
    api(`/skills/${ref}/proposals${llm ? "?llm=true" : ""}`,
        { method: "POST" })
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
  return <Page><h2>Skill Studio</h2>
    {msg && <p style={{ color: "#f88" }}>{msg}</p>}
    <div style={card}>
      <b>Registry ops</b>
      <div style={{ display: "flex", gap: 8, marginTop: 6,
        flexWrap: "wrap", fontSize: 12 }}>
        <input value={newSk} placeholder="new skill id" style={inp}
          onChange={(e) => setNewSk(e.target.value)} />
        <button disabled={!newSk} onClick={() =>
          api("/skills", { method: "POST",
            body: JSON.stringify({ id: newSk }) })
            .then(() => { setMsg(`created ${newSk}`); setNewSk("");
              load(); })
            .catch((e) => setMsg(String(e)))}>New</button>
        <input value={imp} placeholder="path or git url[#subdir]"
          style={{ ...inp, width: 260 }}
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
      <div key={s.id} style={card}>
        <b>{s.id}</b> [{s.status}]
        <button style={{ marginLeft: 8, fontSize: 11 }} onClick={() =>
          show("grad", api(`/skills/${s.id}/graduation`))}>
          Graduation</button>
        {s.variants.map((v) => (
          <span key={v.id} style={{ marginLeft: 8, fontSize: 12 }}>
            <a href="#" onClick={() =>
              api(`/skills/${s.id}@${v.id}/preview`)
                .then((d) => { setPv(d); setPanel(null); })}>
              {v.id}</a>
            {" "}[<a href="#" onClick={() =>
              show("check", api(`/skills/${s.id}@${v.id}/check`))}>
              check</a>]
            {" "}[<a href="#" onClick={() =>
              show("trace", api(`/trace/${s.id}@${v.id}`))}>
              trace</a>]
            {" "}[<a href="#" onClick={() =>
              suggest(`${s.id}@${v.id}`, false)}>propose</a>]
            {" "}<label style={{ fontSize: 10, color: "#888" }}>
              <input type="file" style={{ display: "none" }}
                onChange={(e) => e.target.files[0] &&
                  upload(`${s.id}@${v.id}`, e.target.files[0])} />
              <u style={{ cursor: "pointer" }}>+resource</u></label>
          </span>))}
        </div>))}
    {panel && <div style={card}>
      {panel.kind === "grad" && <>
        <h3>Graduation — {panel.data.skill_id}
          {" "}({panel.data.n_runs} runs)</h3>
        <div style={{ fontSize: 12 }}>
          activation: {panel.data.activation_rate != null
            ? (panel.data.activation_rate * 100).toFixed(0) + "%" : "—"}
          {" · "}false: {panel.data.false_activation_rate != null
            ? (panel.data.false_activation_rate * 100).toFixed(0) + "%"
            : "—"}</div>
        {Object.entries(panel.data.task_deltas || {}).map(([t, d]) =>
          <div key={t} style={{ fontSize: 11 }}>
            Δ {t}: {d > 0 ? "+" : ""}{d.toFixed(2)}</div>)}
        <table style={{ fontSize: 12, marginTop: 6,
          borderCollapse: "collapse" }}>
          <tbody>{panel.data.verdicts.map(([name, ok, detail], i) =>
            <tr key={i}>
              <td style={{ ...td, color: ok === false ? "#f88"
                : ok === true ? "#8f8" : "#aa5" }}>
                {ok == null ? "?" : ok ? "PASS" : "FAIL"}</td>
              <td style={td}><b>{name}</b></td>
              <td style={{ ...td, color: "#888" }}>{detail}</td>
            </tr>)}</tbody></table></>}
      {panel.kind === "check" && <>
        <h3>Skill check</h3>
        <ul style={{ fontSize: 12 }}>{panel.data.map((f, i) =>
          <li key={i} style={{ color: f.severity === "error"
            ? "#f88" : "#aa5" }}>
            [{f.severity}] {f.check}: {f.message}</li>)}
          {!panel.data.length && <li>clean</li>}</ul></>}
      {panel.kind === "proposals" && <>
        <h3>Proposals created</h3>
        <ul style={{ fontSize: 12 }}>{panel.data.map((p) =>
          <li key={p.id}>{p.id} — {p.patch?.summary || p.finding}</li>)}
          {!panel.data.length && <li>no proposals generated</li>}</ul>
        {panel.data.length > 0 && <div style={{ fontSize: 11,
          color: "#888" }}>review on the AI Architect page</div>}</>}
      {panel.kind === "trace" && <TraceView t={panel.data} />}
      {panel.kind === "scan" && <>
        <h3>Discovered skills</h3>
        <ul style={{ fontSize: 12 }}>{panel.data.map((s, i) =>
          <li key={i}><b>{s.name}</b>
            <span style={{ color: "#888" }}> — {s.path}</span></li>)}
          {!panel.data.length && <li>none found</li>}</ul></>}
    </div>}
    {pv && <div style={card}>
      <h3>{pv.ref} — {pv.entry} ~{pv.tokens} tok</h3>
      <pre style={{ fontSize: 12 }}>{JSON.stringify(pv.fm, null, 1)}</pre>
      <b>Sections</b><ul>{pv.sections.map((s, i) =>
        <li key={i}>{s}</li>)}</ul>
      <b>Resources</b><ul>{pv.resources.map((r, i) =>
        <li key={i}>{r}</li>)}</ul></div>}
  </Page>;
}

function TraceView({ t }) {
  return <div style={{ fontSize: 12 }}>
    <h3>Trace: {t.skill}@{t.variant}</h3>
    {t.blueprint
      ? <div>blueprint: <b>{t.blueprint.project}/{t.blueprint.id}</b>
          {" "}r{t.blueprint.rev} (now r{t.blueprint.rev_current})
          {" "}[{t.blueprint.status}] — project: {t.project}</div>
      : <div style={{ color: "#888" }}>no blueprint provenance</div>}
    {t.findings.length > 0 && <div>findings: {t.findings.map((f) =>
      <span key={f.id} style={{ marginRight: 8 }}>
        {f.id}[{f.status}]</span>)}</div>}
    {t.questions.length > 0 && <div>questions: {t.questions.map((q) =>
      <span key={q.id} style={{ marginRight: 8 }}>
        {q.id}[{q.status}]</span>)}</div>}
    {t.experiments.length > 0 && <div>experiments:
      {" "}{t.experiments.join(", ")}</div>}
    {t.runs.length > 0 && <div>runs ({t.runs.length}):
      {" "}{t.runs.slice(0, 6).map((r) =>
        <Link key={r} to={"/runs/" + r} style={{ marginRight: 6 }}>
          <code>{r}</code></Link>)}
      {t.runs.length > 6 && "…"}</div>}
    {t.insights.length > 0 && <div>insights: {t.insights.map((i) =>
      <span key={i.id} style={{ marginRight: 8 }}>
        {i.id}[{i.status}/{i.kind}]</span>)}</div>}
  </div>;
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
  const [rid, setRid] = useState("");
  const [cand, setCand] = useState({});
  const [msg, setMsg] = useState("");
  const load = () => api("/failures").then(setList).catch(() => {});
  useEffect(load, []);
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
  return <Page><h2>Failure Analysis</h2>
    {msg && <p style={{ color: "#8f8" }}>{msg}</p>}
    <div style={{ marginBottom: 8, fontSize: 12 }}>
      <input value={rid} placeholder="run id to analyze"
        style={{ ...inp, width: 340 }}
        onChange={(e) => setRid(e.target.value)} />
      <button onClick={analyze} disabled={!rid}>Analyze run</button>
    </div>
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
        <div style={{ fontSize: 12, marginTop: 6 }}>
          candidate variant:
          <input value={cand[f.run_id] || ""} placeholder="new variant id"
            style={{ ...inp, width: 140 }}
            onChange={(e) => setCand({ ...cand,
              [f.run_id]: e.target.value })} />
          <button disabled={!cand[f.run_id]}
            onClick={() => candidate(f.run_id)}>Create candidate</button>
          <span style={{ color: "#888", fontSize: 11 }}> clones variant +
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
  return <Page><h2>Release Center</h2>
    {msg && <p style={{ color: "#8f8" }}>{msg}</p>}
    <div style={card}>
      <b>New release</b>
      <div style={{ display: "flex", gap: 8, marginTop: 6,
        flexWrap: "wrap" }}>
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
          style={inp} onChange={(e) => setForm({ ...form,
            version: e.target.value })} />
        <input value={form.changelog} placeholder="changelog"
          style={{ ...inp, width: 260 }}
          onChange={(e) => setForm({ ...form,
            changelog: e.target.value })} />
        <button onClick={create}
          disabled={!form.skill || !form.variant || !form.version}>
          Create draft</button>
      </div>
    </div>
    {list.map((r, i) => (
      <div key={i} style={card}>
        <a href="#" onClick={() => open(r)}>
          <b>{r.skill}@{r.version}</b></a>
        {" "}— {r.variant} [{r.status}]
        <span style={{ marginLeft: 10 }}>
          {(NEXT[r.status] || []).map((s) => (
            <button key={s} style={{ marginRight: 4 }}
              onClick={() => setStatus(r, s)}>→ {s}</button>))}
        </span>
        <div style={{ color: "#888", fontSize: 12 }}>{r.changelog}</div>
      </div>))}
    {det && <div style={card}>
      <h3>{det.release.skill}@{det.release.version} — checklist</h3>
      <table style={{ fontSize: 12, borderCollapse: "collapse" }}>
        <thead><tr>{["check","required","ok","detail"].map((h) =>
          <th key={h} style={th}>{h}</th>)}</tr></thead>
        <tbody>{det.checklist.map((c) => <tr key={c.id}>
          <td style={td}><b>{c.id}</b></td>
          <td style={td}>{c.required ? "yes" : "no"}</td>
          <td style={{ ...td, color: c.ok ? "#8f8" : "#f88" }}>
            {c.ok ? "✓" : "✗"}</td>
          <td style={{ ...td, color: "#888" }}>{c.detail}</td>
        </tr>)}</tbody></table>
      {det.release.released_at && <p style={{ fontSize: 11,
        color: "#888" }}>released at {det.release.released_at}</p>}
    </div>}
  </Page>;
}

const inp = { background: "#0a0c0f", color: "#ddd", padding: "4px 6px",
              border: "1px solid #333", width: 140 };

function Knowledge() {
  const [list, setList] = useState([]);
  const [det, setDet] = useState(null);
  const [form, setForm] = useState({ title: "", evidence: "" });
  const [msg, setMsg] = useState("");
  const load = () => api("/insights").then(setList).catch(() => {});
  useEffect(load, []);
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
  return <Page><h2>Knowledge Base</h2>
    {msg && <p style={{ color: "#8f8" }}>{msg}</p>}
    <div style={card}>
      <b>New insight</b>
      <div style={{ display: "flex", gap: 8, marginTop: 6 }}>
        <input value={form.title} placeholder="title"
          style={{ ...inp, width: 300 }}
          onChange={(e) => setForm({ ...form, title: e.target.value })} />
        <input value={form.evidence}
          placeholder="evidence (experiment/run id)"
          style={{ ...inp, width: 300 }}
          onChange={(e) => setForm({ ...form, evidence: e.target.value })} />
        <button onClick={create} disabled={!form.title}>Create</button>
      </div>
    </div>
    {list.map((i) => <div key={i.id} style={card}>
      <a href="#" onClick={() => open(i)}><b>{i.id}</b></a>
      <span style={{ fontSize: 12, color: "#888" }}>
        {" "}[{i.kind}] {i.status} · {i.confidence} ·
        evidence: {(i.evidence || []).join(", ") || "—"}</span>
      {i.kind === "insight" && <span style={{ marginLeft: 10 }}>
        {i.status !== "confirmed" &&
          <button onClick={() => act(i.id, "confirm")}>Confirm</button>}
        {i.status !== "refuted" &&
          <button onClick={() => act(i.id, "refute")}
            style={{ marginLeft: 4 }}>Refute</button>}
        {i.status === "confirmed" &&
          <button onClick={() => act(i.id, "promote")}
            style={{ marginLeft: 4 }}>Promote</button>}
      </span>}
    </div>)}
    {det && <div style={card}>
      <h3>{det.id} <span style={{ color: "#888", fontSize: 12 }}>
        [{det.kind}]</span></h3>
      <table style={{ fontSize: 12, borderCollapse: "collapse" }}>
        <tbody>{Object.entries(det.frontmatter).map(([k, v]) =>
          <tr key={k}>
            <td style={{ ...td, color: "#888" }}>{k}</td>
            <td style={td}>{Array.isArray(v) ? v.join(", ") : String(v)}
            </td></tr>)}</tbody></table>
      <pre style={{ fontSize: 12, whiteSpace: "pre-wrap",
        background: "#0a0c0f", padding: 8, marginTop: 8 }}>{det.body}</pre>
    </div>}
  </Page>;
}

function Regressions() {
  const [list, setList] = useState([]);
  const [skills, setSkills] = useState([]);
  const [det, setDet] = useState(null);
  const [msg, setMsg] = useState("");
  const [form, setForm] = useState({ skill: "", baseline: "",
    candidate: "", tasks: "default", mode: "", rollouts: "" });
  const load = () => api("/regressions").then(setList).catch(() => {});
  useEffect(() => { load();
    api("/skills").then(setSkills).catch(() => {}); }, []);
  const open = (id) => api("/regressions/" + id).then(setDet)
    .catch((e) => setMsg(String(e)));
  const run = () => {
    const body = { skill: form.skill, baseline: form.baseline,
      candidate: form.candidate, tasks: form.tasks || "default" };
    if (form.mode) body.mode = form.mode;
    if (form.rollouts) body.rollouts = parseInt(form.rollouts, 10);
    api("/regressions", { method: "POST", body: JSON.stringify(body) })
      .then((r) => { setMsg(`regression '${r.id}' complete`); load(); })
      .catch((e) => setMsg(String(e)));
  };
  const variants = (skills.find((s) => s.id === form.skill) || {})
    .variants || [];
  const fmt = (m, k, pct) => m && m[k] != null
    ? (pct ? (m[k] * 100).toFixed(0) + "%"
      : typeof m[k] === "number" ? m[k].toFixed(2) : m[k])
    : "—";
  return <Page><h2>Regressions</h2>
    {msg && <p style={{ color: "#8f8" }}>{msg}</p>}
    <div style={card}>
      <b>Run regression</b>
      <div style={{ display: "flex", gap: 8, marginTop: 6,
        flexWrap: "wrap" }}>
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
          style={inp}
          onChange={(e) => setForm({ ...form, tasks: e.target.value })} />
        <select value={form.mode}
          onChange={(e) => setForm({ ...form, mode: e.target.value })}>
          <option value="">mode…</option>
          <option value="available">available</option>
          <option value="injected">injected</option>
        </select>
        <input value={form.rollouts} placeholder="rollouts" type="number"
          style={{ ...inp, width: 80 }}
          onChange={(e) => setForm({ ...form, rollouts: e.target.value })} />
        <button onClick={run}
          disabled={!form.skill || !form.baseline || !form.candidate}>
          Run</button>
      </div>
    </div>
    {list.map((r) => <div key={r.id} style={card}>
      <a href="#" onClick={() => open(r.id)}><b>{r.id}</b></a>
      <span style={{ fontSize: 12, color: "#888" }}>
        {" "}{r.skill} {r.baseline}→{r.candidate} ·
        model {r.model} · {r.tasks?.length || 0} tasks ·
        [{r.status}]</span>
      <b style={{ marginLeft: 8,
        color: r.verdict === "clean" ? "#8f8"
          : r.verdict === "regressed" ? "#f88" : "#aa5" }}>
        {r.verdict || "—"}</b>
    </div>)}
    {det && <div style={card}>
      <h3>{det.meta.id}
        {det.report && <span style={{ fontSize: 12, marginLeft: 8,
          color: det.report.verdict === "clean" ? "#8f8"
            : det.report.verdict === "regressed" ? "#f88" : "#aa5" }}>
          [{det.report.verdict}]</span>}</h3>
      {det.report && <>
        <div style={{ fontSize: 12, color: "#888" }}>
          categories: {Object.entries(det.report.counts || {})
            .filter(([, n]) => n > 0)
            .map(([k, n]) => `${k}=${n}`).join(", ") || "none"}
        </div>
        <table style={{ fontSize: 11, borderCollapse: "collapse",
          marginTop: 8 }}>
          <thead><tr>{["task","kind","categories",
            "base score","cand score","base tok","cand tok",
            "base lat","cand lat"].map((h) =>
              <th key={h} style={th}>{h}</th>)}</tr></thead>
          <tbody>{det.report.tasks.map((t) => <tr key={t.task}>
            <td style={td}><b>{t.task}</b></td>
            <td style={td}>{t.kind}</td>
            <td style={{ ...td,
              color: t.categories.length ? "#f88" : "#8f8" }}>
              {t.categories.join(", ") || "clean"}</td>
            <td style={td}>{fmt(t.baseline, "score")}</td>
            <td style={td}>{fmt(t.candidate, "score")}</td>
            <td style={td}>{fmt(t.baseline, "tokens")}</td>
            <td style={td}>{fmt(t.candidate, "tokens")}</td>
            <td style={td}>{fmt(t.baseline, "latency")}</td>
            <td style={td}>{fmt(t.candidate, "latency")}</td>
          </tr>)}</tbody></table></>}
      {det.markdown && <pre style={{ fontSize: 11,
        whiteSpace: "pre-wrap", maxHeight: 300, overflow: "auto",
        background: "#0a0c0f", padding: 8, marginTop: 8 }}>
        {det.markdown}</pre>}
    </div>}
  </Page>;
}

function Experiments() {
  const [list, setList] = useState([]);
  const [msg, setMsg] = useState("");
  const [runs, setRuns] = useState([]);
  const [cmp, setCmp] = useState({});
  const [rep, setRep] = useState({});
  const [panel, setPanel] = useState({});
  const [aux, setAux] = useState({ batch: "", model: "", limit: "",
    conclusion: "", a: "", b: "", newExp: "", newCat: "trigger" });
  const load = () => {
    api("/experiments").then(setList).catch(() => {});
    api("/runs").then(setRuns).catch(() => {});
  };
  useEffect(load, []);
  const run = (id) =>
    api(`/experiments/${id}/run`, { method: "POST" })
      .then((r) => { setMsg(`${id}: ${r.count} runs`); load(); })
      .catch((e) => setMsg(String(e)));
  const rerun = (id) => {
    const body = {};
    if (aux.batch) body.batch = aux.batch;
    if (aux.model) body.model = aux.model;
    if (aux.limit) body.limit = parseInt(aux.limit, 10);
    api(`/experiments/${id}/rerun`, { method: "POST",
      body: JSON.stringify(body) })
      .then((r) => { setMsg(`${id}: ${r.count} runs (batch
        ${r.batch || "—"})`); load(); })
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
      .then(() => { setMsg(`created ${aux.newExp} — fill arms/tasks`);
        setAux({ ...aux, newExp: "" }); load(); })
      .catch((e) => setMsg(String(e)));
  const ax = (k) => ({ value: aux[k],
    onChange: (e) => setAux({ ...aux, [k]: e.target.value }) });
  return <Page><h2>Experiment Lab</h2>
    {msg && <p style={{ color: "#8f8" }}>{msg}</p>}
    <div style={{ fontSize: 12, marginBottom: 8 }}>
      <input {...ax("newExp")} placeholder="new experiment id"
        style={inp} />
      <select value={aux.newCat} style={{ fontSize: 11 }}
        onChange={(e) => setAux({ ...aux, newCat: e.target.value })}>
        {["capability","trigger","workflow","instruction","resource",
          "tool-use","compatibility","reliability","efficiency"]
          .map((c) => <option key={c}>{c}</option>)}
      </select>
      <button onClick={create} disabled={!aux.newExp}>Create</button>
      <span style={{ marginLeft: 16 }}>diff:
        <input {...ax("a")} placeholder="run A"
          style={{ ...inp, width: 220 }} />
        <input {...ax("b")} placeholder="run B"
          style={{ ...inp, width: 220 }} />
        <button onClick={diff} disabled={!aux.a || !aux.b}>
          Diff runs</button></span>
    </div>
    {panel._diff && <div style={card}>
      <b>{panel._diff.data.run_a} vs {panel._diff.data.run_b}</b>
      <pre style={{ fontSize: 10, maxHeight: 200, overflow: "auto",
        background: "#0a0c0f", padding: 6 }}>
        {panel._diff.data.transcript_diff.join("\n") ||
          "(transcripts identical)"}</pre>
      {(panel._diff.data.added.length > 0 ||
        panel._diff.data.removed.length > 0) &&
        <div style={{ fontSize: 11 }}>
          {panel._diff.data.added.map((f) =>
            <div key={f} style={{ color: "#8f8" }}>+ {f}</div>)}
          {panel._diff.data.removed.map((f) =>
            <div key={f} style={{ color: "#f88" }}>- {f}</div>)}
        </div>}
    </div>}
    {list.map((e) => <div key={e.id} style={card}>
      <b>{e.id}</b> [{e.status}] {e.title}
      <span style={{ color: "#5af", fontSize: 11 }}>
        {" "}{e.category || ""}</span>
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
      <button onClick={() => show(e.id, "validate",
          api(`/experiments/${e.id}/validate`))}
        style={{ marginLeft: 6 }}>Validate</button>
      <button onClick={() => show(e.id, "runs",
          api(`/experiments/${e.id}/runs`))}
        style={{ marginLeft: 6 }}>Runs</button>
      {e.status !== "concluded" && <>
        <span style={{ marginLeft: 10, fontSize: 11 }}>rerun:
          <input {...ax("batch")} placeholder="batch"
            style={{ ...inp, width: 90 }} />
          <input {...ax("model")} placeholder="model"
            style={{ ...inp, width: 110 }} />
          <input {...ax("limit")} placeholder="limit" type="number"
            style={{ ...inp, width: 60 }} />
          <button onClick={() => rerun(e.id)}>Go</button></span>
        <span style={{ marginLeft: 10, fontSize: 11 }}>
          <input {...ax("conclusion")} placeholder="conclusion"
            style={{ ...inp, width: 160 }} />
          <button onClick={() => conclude(e.id)}
            disabled={!aux.conclusion}>Conclude</button></span></>}
      {panel[e.id]?.key === "validate" && <div style={{ fontSize: 11,
        marginTop: 6 }}>
        {panel[e.id].data.valid
          ? <span style={{ color: "#8f8" }}>valid</span>
          : panel[e.id].data.errors.map((x, i) =>
            <div key={i} style={{ color: "#f88" }}>error: {x}</div>)}
        {panel[e.id].data.warnings.map((w, i) =>
          <div key={i} style={{ color: "#aa5" }}>warn: {w}</div>)}
      </div>}
      {panel[e.id]?.key === "runs" && <div style={{ fontSize: 11,
        marginTop: 6 }}>
        {panel[e.id].data.map((x) =>
          <div key={x.run.run_id}>
            <Link to={"/runs/" + x.run.run_id}>
              <code>{x.run.run_id}</code></Link>
            {" "}[{x.run.status}] eval:
            {" "}{x.eval ? x.eval.status : "—"}</div>)}
        {!panel[e.id].data.length && "no runs yet"}
      </div>}
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
  return <Page><h2>Blueprints</h2>
    {msg && <p style={{ color: "#f88" }}>{msg}</p>}
    {projects.map((p) => (
      <button key={p.id} onClick={() => pick(p.id)}
        style={{ marginRight: 8 }}>{p.id}</button>))}
    {bpPid && <div style={{ marginTop: 8 }}>
      <input value={newBp} placeholder="new blueprint id" style={inp}
        onChange={(e) => setNewBp(e.target.value)} />
      <button onClick={create} disabled={!newBp}>Create</button></div>}
    {sel && sel.map((b) => <div key={b.id} style={card}>
      <b>{b.id}</b> [{b.status}] rev {b.rev} — {b.title}
      <div style={{ fontSize: 12, color: "#888" }}>
        findings: {(b.related_findings || []).join(", ") || "—"} ·
        generated: {(b.generated_variants || []).join(", ") || "—"}</div>
      <BpActions pid={bpPid} b={b} proj={proj}
        reload={() => pick(bpPid)} onErr={setMsg} />
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
  const btn = { marginRight: 4, fontSize: 11 };
  return <div style={{ fontSize: 12, margin: "6px 0" }}>
    <StatusSel value={b.status}
      options={["draft","designing","ready_for_generation","generated",
        "testing","improving","validated","released","archived"]}
      onChange={(s) => post(`${B}/status`, { status: s })} />
    <button style={btn} onClick={() => get(`${B}/validate`, "validate")}>
      Validate</button>
    <button style={btn} onClick={() =>
      post(`${B}/draft`, {}, (r) => { setPanel("draft"); setData(r); })}>
      Draft from research</button>
    <button style={btn} onClick={() => get(`${B}/revisions`, "revs")}>
      Revisions</button>
    <div style={{ margin: "4px 0" }}>
      {proj && <>
        <select value={aux.qid} style={{ fontSize: 11 }}
          onChange={(e) => setAux({ ...aux, qid: e.target.value })}>
          <option value="">question…</option>
          {proj.questions.map((q) =>
            <option key={q.id} value={q.id}>{q.id}</option>)}
        </select>
        <button style={btn} disabled={!aux.qid}
          onClick={() => post(`${B}/from-question`, { qid: aux.qid })}>
          Prefill</button>
        <select value={aux.finding} style={{ fontSize: 11 }}
          onChange={(e) => setAux({ ...aux, finding: e.target.value })}>
          <option value="">finding…</option>
          {proj.findings.map((f) =>
            <option key={f.id} value={f.id}>{f.id}</option>)}
        </select>
        <button style={btn} disabled={!aux.finding}
          onClick={() => post(`${B}/link`, { finding: aux.finding })}>
          Link</button>
      </>}
    </div>
    <div style={{ margin: "4px 0" }}>
      generate: <input value={aux.skill} placeholder="skill"
        style={{ ...inp, width: 110 }}
        onChange={(e) => setAux({ ...aux, skill: e.target.value })} />
      <input value={aux.variant} placeholder="variant"
        style={{ ...inp, width: 80 }}
        onChange={(e) => setAux({ ...aux, variant: e.target.value })} />
      <select value={aux.format} style={{ fontSize: 11 }}
        onChange={(e) => setAux({ ...aux, format: e.target.value })}>
        <option value="skill-md">skill-md</option>
        <option value="system-prompt">system-prompt</option>
      </select>
      <label style={{ fontSize: 11 }}><input type="checkbox"
        checked={aux.force}
        onChange={(e) => setAux({ ...aux, force: e.target.checked })} />
        force</label>
      <button style={btn} disabled={!aux.skill || !aux.variant}
        onClick={() => post(`${B}/generate`,
          { skill: aux.skill, variant: aux.variant,
            format: aux.format, force: aux.force })}>Generate</button>
    </div>
    <div style={{ margin: "4px 0" }}>
      scaffold: <input value={aux.exp_id} placeholder="exp id (opt)"
        style={{ ...inp, width: 110 }}
        onChange={(e) => setAux({ ...aux, exp_id: e.target.value })} />
      <button style={btn} disabled={!aux.skill || !aux.variant}
        onClick={() => post(`${B}/experiment`,
          { skill: aux.skill, variant: aux.variant,
            exp_id: aux.exp_id || null },
          (r) => { setPanel("exp"); setData(r); })}>Experiment</button>
      drift: <input value={aux.ref} placeholder="skill@variant"
        style={{ ...inp, width: 150 }}
        onChange={(e) => setAux({ ...aux, ref: e.target.value })} />
      <button style={btn} disabled={!aux.ref}
        onClick={() => get(`${B}/drift?ref=${encodeURIComponent(aux.ref)}`,
          "drift")}>Check drift</button>
      diff: <input value={aux.from_rev} placeholder="from rev" type="number"
        style={{ ...inp, width: 70 }}
        onChange={(e) => setAux({ ...aux, from_rev: e.target.value })} />
      <button style={btn} disabled={!aux.from_rev}
        onClick={() => get(`${B}/diff?from_rev=${aux.from_rev}`,
          "diff")}>Diff→now</button>
    </div>
    {panel === "validate" && data && <table style={{ fontSize: 11,
      borderCollapse: "collapse" }}>
      <tbody>{data.map((i, k) => <tr key={k}>
        <td style={{ ...td,
          color: i.severity === "error" ? "#f88" : "#aa5" }}>
          {i.severity}</td>
        <td style={td}>{i.check}</td>
        <td style={td}>{i.field || ""}</td>
        <td style={td}>{i.message}</td></tr>)}
      {!data.length && <tr><td style={td}>no issues</td></tr>}
      </tbody></table>}
    {panel === "draft" && data && <div style={{ fontSize: 11,
      color: "#ad7" }}>touched: {data.touched.join(", ") || "none"}
    </div>}
    {panel === "exp" && data && <div style={{ fontSize: 11,
      color: "#ad7" }}>experiment {data.experiment} — created:
      {" "}{data.tasks_created.join(", ") || "—"}; skipped:
      {" "}{data.tasks_skipped.join(", ") || "—"}</div>}
    {panel === "revs" && data && <ul style={{ fontSize: 11 }}>
      {data.map((r) => <li key={r.rev}>r{r.rev} [{r.status}]
        {" "}{r.updated}</li>)}</ul>}
    {panel === "diff" && data && <ul style={{ fontSize: 11 }}>
      {(data.diffs || []).map((d, k) => <li key={k}>
        <b>{d.field}</b>: {String(d.from).slice(0, 50)} →
        {" "}{String(d.to).slice(0, 50)}</li>)}
      {!data.diffs?.length && <li>no field changes</li>}</ul>}
    {panel === "drift" && data && <div style={{ fontSize: 11 }}>
      <b style={{ color: data.status === "synced" ? "#8f8" : "#f88" }}>
        {data.status}</b>
      {" "}gen@r{data.gen_rev ?? "?"} vs bp r{data.bp_rev}
      {data.diff && <pre style={{ maxHeight: 160, overflow: "auto",
        background: "#0a0c0f", padding: 6, fontSize: 10 }}>
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

function AddForm({ ph, onAdd }) {
  const [v, setV] = useState("");
  return <span>
    <input value={v} placeholder={ph}
      onChange={(e) => setV(e.target.value)}
      onKeyDown={(e) => e.key === "Enter" && v && (onAdd(v), setV(""))}
      style={{ background: "#0a0c0f", color: "#ddd", padding: "3px 6px",
               border: "1px solid #333", width: 280,
               fontSize: 12 }} />
    <button disabled={!v} style={{ marginLeft: 6 }}
      onClick={() => { onAdd(v); setV(""); }}>+</button>
  </span>;
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
    <Route path="/regressions" element={<Regressions />} />
    <Route path="/proposals" element={<Proposals />} />
    <Route path="/failures" element={<Failures />} />
    <Route path="/knowledge" element={<Knowledge />} />
    <Route path="/releases" element={<Releases />} />
  </Routes></>);
}
// blueprint field editor appended in Blueprints page
