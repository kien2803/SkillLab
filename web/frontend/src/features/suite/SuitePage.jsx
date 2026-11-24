// Test Suite workspace — visual management of tasks, rubrics, named
// suites, fixtures and datasets. Validation comes from
// GET /suite/validate (server-side — same rules the engine enforces);
// the UI never re-decides what counts as runnable.
import React, { useEffect, useMemo, useRef, useState } from "react";
import { api, apiFetch } from "../../api.js";
import "./suite.css";

const KINDS = ["performance", "activation-positive",
               "activation-negative"];
const KIND_BLURB = {
  "performance": "scores task success/correctness vs a rubric",
  "activation-positive": "the named skill SHOULD trigger here",
  "activation-negative": "the named skill should NOT trigger here",
};
const CHECK_TYPES = ["command", "file-exists", "file-content",
                     "script", "json"];
const METHODS = ["deterministic", "llm-judge", "human"];
const blank = () => ({ id: "", kind: "performance", prompt: "",
  fixtures: [], skill_relevance: { expected: [], unexpected: [] },
  rubric: null, deterministic_checks: [] });
const clone = (o) => JSON.parse(JSON.stringify(o));
const eq = (a, b) => JSON.stringify(a) === JSON.stringify(b);

/* ---------- small bits ---------- */

const Dot = ({ issues }) => {
  const sev = (issues || []).some((i) => i.severity === "error")
    ? "err" : (issues || []).length ? "warn" : "ok";
  return <span className={"dot " + sev}
    title={sev === "err" ? "has errors — cannot benchmark" :
      sev === "warn" ? "has warnings" : "clean"} />;
};

const IssueList = ({ issues }) =>
  !issues?.length ? null : <div className="iss">
    {issues.map((i, k) => <div key={k} className="row">
      <span className={"sev " + i.severity}>{i.severity}</span>
      <span className="fld-name">{i.field}</span>
      <span>{i.message}</span>
      {i.fix && <span className="fix">{i.fix}</span>}
    </div>)}
  </div>;

const Field = ({ label, req, help, children }) =>
  <label className="fld"><span><b>{label}</b>
    {req && <span className="req"> *</span>}</span>
    {children}
    {help && <span className="help">{help}</span>}
  </label>;

/* ---------- task editor ---------- */

function CheckEditor({ c, onChange, onRemove }) {
  const set = (k, v) => onChange({ ...c, [k]: v });
  return <div className="check-row">
    <div className="top">
      <select value={c.type}
        onChange={(e) => set("type", e.target.value)}>
        {CHECK_TYPES.map((t) => <option key={t}>{t}</option>)}
      </select>
      <input placeholder="check id (optional)" value={c.id || ""}
        style={{ width: 160 }}
        onChange={(e) => set("id", e.target.value || null)} />
      <button className="link x" onClick={onRemove}>remove</button>
    </div>
    <div className="ts-grid" style={{ marginTop: 10 }}>
      {c.type === "command" && <Field label="command" req
        help="runs in the run workspace under the lab sandbox policy">
        <input value={c.command || ""}
          onChange={(e) => set("command", e.target.value)} />
      </Field>}
      {["file-exists", "file-content", "script", "json"].includes(
        c.type) && <Field label="path" req
          help="file the agent is expected to produce">
        <input value={c.path || ""}
          onChange={(e) => set("path", e.target.value)} />
      </Field>}
      {c.type === "file-content" && <>
        <Field label="contains" help="literal substring required">
          <input value={c.contains || ""}
            onChange={(e) => set("contains", e.target.value)} />
        </Field>
        <Field label="regex" help="pattern that must match">
          <input value={c.regex || ""}
            onChange={(e) => set("regex", e.target.value)} />
        </Field>
        <Field label="equals" help="whole-file comparison">
          <input value={c.equals || ""}
            onChange={(e) => set("equals", e.target.value)} />
        </Field>
      </>}
      {c.type === "json" && <>
        <Field label="keys" help="comma-separated required top-level keys">
          <input value={(c.keys || []).join(", ")}
            onChange={(e) => set("keys", e.target.value.split(",")
              .map((s) => s.trim()).filter(Boolean))} />
        </Field>
        <Field label="field" help="dotted path to compare">
          <input value={c.field || ""}
            onChange={(e) => set("field", e.target.value)} />
        </Field>
        <Field label="value" help="expected scalar for field">
          <input value={c.value || ""}
            onChange={(e) => set("value", e.target.value)} />
        </Field>
      </>}
    </div>
  </div>;
}

function TaskEditor({ tid, rubrics, onChanged, onDeleted }) {
  const [det, setDet] = useState(null);      // server detail
  const [draft, setDraft] = useState(null);  // editable copy
  const [tab, setTab] = useState("general");
  const [msg, setMsg] = useState("");
  const [fileForm, setFileForm] = useState({ path: "", content: "" });
  const load = () => api(`/tasks/${encodeURIComponent(tid)}`)
    .then((d) => { setDet(d); setDraft(clone(d.task)); })
    .catch((e) => setMsg(String(e)));
  useEffect(() => { setDet(null); setDraft(null); setTab("general");
    setMsg(""); load(); }, [tid]);
  useEffect(() => {
    const h = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "s") {
        e.preventDefault(); save();
      }
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  });
  if (!draft) return <div className="card ts-empty">
    {msg || "loading…"}</div>;

  const dirty = det && !eq(draft, det.task);
  const issues = det?.issues || [];
  const tabIssues = (fields) => issues.filter((i) =>
    fields.some((f) => i.field.startsWith(f))).length;
  const set = (k, v) => setDraft({ ...draft, [k]: v });
  const setSR = (k, v) => setDraft({ ...draft,
    skill_relevance: { ...draft.skill_relevance,
      [k]: v.split(",").map((s) => s.trim()).filter(Boolean) } });

  const save = () => {
    api(`/tasks/${encodeURIComponent(tid)}`,
        { method: "PUT", body: JSON.stringify(draft) })
      .then((r) => { setDet({ ...det, task: r.task, issues: r.issues });
        setDraft(clone(r.task)); setMsg("saved");
        if (r.task.id !== tid) onDeleted && onDeleted(tid, r.task.id);
        else onChanged(); })
      .catch((e) => setMsg(String(e)));
  };
  const dup = () => {
    const nid = window.prompt("duplicate as task id:",
      tid + "-copy");
    if (!nid) return;
    api(`/tasks/${encodeURIComponent(tid)}/duplicate`,
        { method: "POST", body: JSON.stringify({ id: nid }) })
      .then(() => onChanged()).catch((e) => setMsg(String(e)));
  };
  const del = () => {
    const refs = det?.refs || { experiments: [], suites: [] };
    const used = [...refs.experiments.map((e) => `experiment ${e}`),
      ...refs.suites.map((s) => `suite ${s}`)];
    const note = used.length
      ? `\n\nReferenced by: ${used.join(", ")} — deleting archives ` +
        "the task anyway; recorded run evidence stays intact."
      : "";
    if (!window.confirm(`Archive task '${tid}'? Historical runs keep ` +
      `their recorded data.${note}`)) return;
    api(`/tasks/${encodeURIComponent(tid)}` +
        (used.length ? "?force=true" : ""), { method: "DELETE" })
      .then(() => onDeleted(tid))
      .catch((e) => setMsg(String(e)));
  };
  const addFile = () => {
    if (!fileForm.path.trim()) return;
    api(`/tasks/${encodeURIComponent(tid)}/file`,
        { method: "PUT", body: JSON.stringify(fileForm) })
      .then(() => { setFileForm({ path: "", content: "" }); load(); })
      .catch((e) => setMsg(String(e)));
  };
  const delFile = (p) => {
    if (!window.confirm(`Delete ${p} from the task dir?`)) return;
    api(`/tasks/${encodeURIComponent(tid)}/file?path=` +
        encodeURIComponent(p), { method: "DELETE" })
      .then(load).catch((e) => setMsg(String(e)));
  };

  const t = (name, fields) => <button
    className={tab === name ? "on" : ""} onClick={() => setTab(name)}>
    {name}{tabIssues(fields) > 0 &&
      <span className="bub">{tabIssues(fields)}</span>}</button>;

  return <div className="card tsed">
    <div className="tsed-head">
      <h3>{tid}{draft.id !== tid && <span className="mut small">
        {" "}→ {draft.id}</span>}</h3>
      <span className="pill acc">{draft.kind}</span>
      <button className="link" onClick={dup}>duplicate</button>
      <button className="link" style={{ color: "var(--negative)" }}
        onClick={del}>archive</button>
    </div>
    <div className="tsed-tabs" role="tablist">
      {t("general", ["kind", "id", "runnable"])}
      {t("input", ["prompt"])}
      {t("evaluation", ["rubric", "criteria", "checks",
        "skill_relevance"])}
      {t("fixtures", ["fixtures"])}
    </div>
    <div className="tsed-body">
      {tab === "general" && <div className="ts-grid">
        <Field label="task id" req
          help="directory name under tasks/ — renaming moves it">
          <input value={draft.id}
            onChange={(e) => set("id", e.target.value)} />
        </Field>
        <Field label="kind" req help={KIND_BLURB[draft.kind]}>
          <select value={draft.kind}
            onChange={(e) => set("kind", e.target.value)}>
            {KINDS.map((k) => <option key={k}>{k}</option>)}
          </select>
        </Field>
        <Field label="referenced by" help="experiments and suites using this task">
          <span className="mut">{[...(det?.refs?.experiments || []),
            ...(det?.refs?.suites || [])].join(", ") || "nothing"}</span>
        </Field>
      </div>}

      {tab === "input" && <>
        <Field label="prompt" req
          help="what the agent is asked to do — inline text, or a file name inside the task dir (e.g. prompt.md)">
          <textarea rows={9} value={draft.prompt}
            onChange={(e) => set("prompt", e.target.value)} />
        </Field>
        {det?.resolved_prompt && det.resolved_prompt !== draft.prompt &&
          <div className="help" style={{ marginTop: 8 }}>resolved
            prompt (from file): <pre className="small"
            style={{ whiteSpace: "pre-wrap", margin: "6px 0 0" }}>
            {det.resolved_prompt.slice(0, 600)}</pre></div>}
      </>}

      {tab === "evaluation" && <>
        <div className="ts-grid">
          <Field label="rubric" help="scored criteria — leave unset for deterministic checks only">
            <select value={draft.rubric || ""}
              onChange={(e) => set("rubric", e.target.value || null)}>
              <option value="">none (deterministic checks only)</option>
              {rubrics.map((r) => <option key={r.id}
                value={r.id}>{r.id}</option>)}
            </select>
          </Field>
          <Field label="expected skills" help="comma-separated — should activate on this task">
            <input value={(draft.skill_relevance?.expected || [])
              .join(", ")}
              onChange={(e) => setSR("expected", e.target.value)} />
          </Field>
          <Field label="unexpected skills" help="comma-separated — should NOT activate">
            <input value={(draft.skill_relevance?.unexpected || [])
              .join(", ")}
              onChange={(e) => setSR("unexpected", e.target.value)} />
          </Field>
        </div>
        <h4 style={{ margin: "18px 0 10px" }}>deterministic checks</h4>
        {(draft.deterministic_checks || []).map((c, i) =>
          <CheckEditor key={i} c={c}
            onChange={(nc) => set("deterministic_checks",
              draft.deterministic_checks.map((x, j) =>
                j === i ? nc : x))}
            onRemove={() => set("deterministic_checks",
              draft.deterministic_checks.filter((_, j) => j !== i))} />)}
        <button className="link" onClick={() =>
          set("deterministic_checks",
            [...(draft.deterministic_checks || []),
             { type: "file-exists", path: "" }])}>
          + add check</button>
      </>}

      {tab === "fixtures" && <>
        <Field label="fixture directories" req={false}
          help="comma-separated directory names inside this task dir — each is copied into the run workspace (files are silently ignored, dirs only)">
          <input value={(draft.fixtures || []).join(", ")}
            onChange={(e) => set("fixtures", e.target.value.split(",")
              .map((s) => s.trim()).filter(Boolean))} />
        </Field>
        <h4 style={{ margin: "18px 0 8px" }}>task dir files</h4>
        <table className="tbl file-list"><tbody>
          {(det?.files || []).filter((f) => f.path !== "task.yaml")
            .map((f) => <tr key={f.path}>
            <td>{f.dir ? "📁 " : ""}{f.path}</td>
            <td className="mut">{f.fixture ? "fixture" : ""}</td>
            <td className="num mut">{f.size ?? ""}</td>
            <td className="r"><button className="link"
              onClick={() => delFile(f.path)}>delete</button></td>
          </tr>)}
        </tbody></table>
        <h4 style={{ margin: "18px 0 8px" }}>add file</h4>
        <div className="ts-grid">
          <Field label="path" help="relative to the task dir, e.g. src/app.py">
            <input value={fileForm.path}
              onChange={(e) => setFileForm({ ...fileForm,
                path: e.target.value })} />
          </Field>
        </div>
        <Field label="content">
          <textarea rows={4} value={fileForm.content}
            onChange={(e) => setFileForm({ ...fileForm,
              content: e.target.value })} />
        </Field>
        <button className="link" onClick={addFile}
          disabled={!fileForm.path.trim()}>upload</button>
      </>}
    </div>
    <IssueList issues={issues} />
    <div className="tsed-foot">
      <button className="primary" onClick={save}
        disabled={!dirty || !draft.id.trim()}>save task</button>
      <button className="link" disabled={!dirty}
        onClick={() => setDraft(clone(det.task))}>revert</button>
      {dirty
        ? <span className="dirty">unsaved changes</span>
        : msg === "saved" && <span className="saved">saved</span>}
      <span className="mut small" style={{ marginLeft: "auto" }}>
        {msg !== "saved" ? msg : "ctrl+s saves"}
      </span>
    </div>
  </div>;
}

/* ---------- rubric editor ---------- */

function RubricEditor({ rid, onChanged, onDeleted }) {
  const [det, setDet] = useState(null);
  const [draft, setDraft] = useState(null);
  const [msg, setMsg] = useState("");
  const load = () => api(`/rubrics/${encodeURIComponent(rid)}`)
    .then((d) => { setDet(d); setDraft(clone(d.rubric)); })
    .catch((e) => setMsg(String(e)));
  useEffect(() => { setDet(null); setDraft(null); setMsg("");
    load(); }, [rid]);
  if (!draft) return <div className="card ts-empty">{msg || "loading…"}</div>;

  const dirty = det && !eq(draft, det.rubric);
  const setC = (i, k, v) => setDraft({ ...draft,
    criteria: draft.criteria.map((c, j) =>
      j === i ? { ...c, [k]: v } : c) });
  const save = () => api(`/rubrics/${encodeURIComponent(rid)}`,
    { method: "PUT", body: JSON.stringify(draft) })
    .then((r) => { setDet({ ...det, rubric: r.rubric,
      issues: r.issues }); setDraft(clone(r.rubric));
      setMsg("saved"); onChanged(); })
    .catch((e) => setMsg(String(e)));
  const del = () => {
    const used = det?.used_by || [];
    const note = used.length ? `\nUsed by tasks: ${used.join(", ")} — ` +
      "deleting leaves them pointing at a missing rubric." : "";
    if (!window.confirm(`Archive rubric '${rid}'?${note}`)) return;
    api(`/rubrics/${encodeURIComponent(rid)}` +
        (used.length ? "?force=true" : ""), { method: "DELETE" })
      .then(() => onDeleted(rid)).catch((e) => setMsg(String(e)));
  };

  return <div className="card tsed">
    <div className="tsed-head">
      <h3>{rid}</h3>
      <span className="mut small">{(det?.used_by || []).length} task(s)
        use it</span>
      <button className="link" style={{ color: "var(--negative)",
        marginLeft: "auto" }} onClick={del}>archive</button>
    </div>
    <div className="tsed-body">
      {draft.criteria.map((c, i) => <div key={i} className="crit-row">
        <div className="top">
          <input value={c.id} placeholder="criterion id"
            style={{ width: 180 }}
            onChange={(e) => setC(i, "id", e.target.value)} />
          <select value={c.method}
            onChange={(e) => setC(i, "method", e.target.value)}>
            {METHODS.map((m) => <option key={m}>{m}</option>)}
          </select>
          <label className="mut small">weight
            <input type="number" step="0.1" value={c.weight}
              style={{ width: 70, marginLeft: 6 }}
              onChange={(e) => setC(i, "weight",
                parseFloat(e.target.value) || 0)} /></label>
          <label className="mut small">scale
            <input value={c.scale || "1-5"}
              style={{ width: 60, marginLeft: 6 }}
              onChange={(e) => setC(i, "scale", e.target.value)} /></label>
          <button className="link x" onClick={() =>
            setDraft({ ...draft, criteria: draft.criteria
              .filter((_, j) => j !== i) })}>remove</button>
        </div>
        <div className="ts-grid" style={{ marginTop: 10 }}>
          {c.method === "deterministic" &&
            <Field label="check" req
              help="id/name of a deterministic check on the task">
              <input value={c.check || ""}
                onChange={(e) => setC(i, "check", e.target.value)} />
            </Field>}
          {c.method === "llm-judge" &&
            <Field label="judge prompt"
              help="what the judge scores — inline text or a file next to the rubric">
              <textarea rows={2} value={c.judge_prompt || ""}
                onChange={(e) => setC(i, "judge_prompt",
                  e.target.value)} />
            </Field>}
          {c.method === "human" &&
            <span className="help">stays 'pending' until a human scores
              it via run scoring — blocks 'passed' status.</span>}
        </div>
      </div>)}
      <button className="link" onClick={() => setDraft({ ...draft,
        criteria: [...draft.criteria, { id: `c${draft.criteria.length + 1}`,
          weight: 1.0, method: "deterministic", check: "",
          scale: "1-5" }] })}>+ add criterion</button>
    </div>
    <IssueList issues={det?.issues} />
    <div className="tsed-foot">
      <button className="primary" onClick={save}
        disabled={!dirty}>save rubric</button>
      <button className="link" disabled={!dirty}
        onClick={() => setDraft(clone(det.rubric))}>revert</button>
      {dirty && <span className="dirty">unsaved changes</span>}
      {msg && <span className="mut small">{msg}</span>}
    </div>
  </div>;
}

/* ---------- named suite editor ---------- */

function SuiteEditor({ sid, tasks, runnable, onChanged, onDeleted }) {
  const [sel, setSel] = useState([]);
  const [msg, setMsg] = useState("");
  useEffect(() => {
    api(`/suites`).then((all) => {
      const s = all.find((x) => x.id === sid);
      setSel(s ? s.tasks : []);
    }).catch((e) => setMsg(String(e)));
  }, [sid]);
  const dirty = true;                       // save always allowed
  const save = () => api(`/suites/${encodeURIComponent(sid)}`,
    { method: "PUT", body: JSON.stringify({ tasks: sel }) })
    .then(() => { setMsg("saved"); onChanged(); })
    .catch((e) => setMsg(String(e)));
  return <div className="card tsed">
    <div className="tsed-head"><h3>{sid}</h3>
      <span className="mut small">{sel.length} task(s)</span>
      <button className="link" style={{ color: "var(--negative)",
        marginLeft: "auto" }} onClick={() => {
        if (window.confirm(`Archive suite '${sid}'?`))
          api(`/suites/${encodeURIComponent(sid)}`,
            { method: "DELETE" }).then(() => onDeleted(sid))
            .catch((e) => setMsg(String(e)));
      }}>archive</button></div>
    <div className="tsed-body suite-checks">
      {tasks.map((t) => {
        const bad = runnable && runnable[t.id] === false;
        return <label key={t.id}>
          <input type="checkbox" checked={sel.includes(t.id)}
            disabled={bad}
            title={bad ? "has errors — fix it before adding to a suite"
              : t.id}
            onChange={(e) => setSel(e.target.checked
              ? [...sel, t.id] : sel.filter((x) => x !== t.id))} />
          {t.id} <span className="mut small">{t.kind}</span>
          {bad && <span className="pill neg"
            style={{ marginLeft: 8 }}>invalid</span>}
        </label>;
      })}
    </div>
    <div className="tsed-foot">
      <button className="primary" onClick={save}>save suite</button>
      {msg && <span className="mut small">{msg}</span>}
    </div>
  </div>;
}

/* ---------- import dialog ---------- */

function ImportDialog({ onClose, onDone }) {
  const [fmt, setFmt] = useState("json");
  const [data, setData] = useState("");
  const [prev, setPrev] = useState(null);
  const [conflict, setConflict] = useState("skip");
  const [msg, setMsg] = useState("");
  const fileRef = useRef();
  const pick = (f) => {
    if (!f) return;
    const rd = new FileReader();
    rd.onload = () => setData(String(rd.result));
    rd.readAsText(f);
    if (f.name.endsWith(".csv")) setFmt("csv");
    else setFmt("json");
  };
  const preview = () => api("/suite/import", { method: "POST",
    body: JSON.stringify({ format: fmt, data, confirm: false }) })
    .then(setPrev).catch((e) => setMsg(String(e)));
  const apply = () => api("/suite/import", { method: "POST",
    body: JSON.stringify({ format: fmt, data, confirm: true,
      on_conflict: conflict }) })
    .then((r) => { onDone(`imported ${r.imported.length}` +
      (r.skipped.length ? `, skipped ${r.skipped.length}` : "") +
      (r.rejected.length ? `, rejected ${r.rejected.length}` : ""));
      onClose(); })
    .catch((e) => setMsg(String(e)));

  return <div className="dlg" onClick={onClose}>
    <div className="box" onClick={(e) => e.stopPropagation()}>
      <h3>Import dataset</h3>
      <div className="toolbar" style={{ marginBottom: 10 }}>
        <select value={fmt} onChange={(e) => setFmt(e.target.value)}>
          <option value="json">JSON array</option>
          <option value="csv">CSV</option>
        </select>
        <button onClick={() => fileRef.current.click()}>
          choose file…</button>
        <input ref={fileRef} type="file" accept=".json,.csv"
          style={{ display: "none" }}
          onChange={(e) => pick(e.target.files[0])} />
      </div>
      <textarea rows={8} style={{ width: "100%" }}
        placeholder={'[{"id":"task-1","kind":"performance",' +
          '"prompt":"…"}]'}
        value={data} onChange={(e) => setData(e.target.value)} />
      <div className="toolbar" style={{ marginTop: 10 }}>
        <button onClick={preview} disabled={!data.trim()}>
          preview</button>
        {prev && <span className="mut small">
          {prev.ok.length} valid · {prev.bad.length +
            prev.parse_errors.length} invalid
          {prev.conflicts.length > 0 &&
            ` · ${prev.conflicts.length} conflict(s)`}
        </span>}
      </div>
      {prev && <div className="imp-preview" style={{ marginTop: 10 }}>
        {(prev.parse_errors || []).map((e, i) =>
          <div key={"p" + i} className="small bad">row {e.row}: {e.error}</div>)}
        {prev.bad.map((b, i) =>
          <div key={"b" + i} className="small bad">row {b.row}
            {" "}({b.id}): {b.error}</div>)}
        {prev.ok.slice(0, 20).map((o, i) =>
          <div key={"o" + i} className="small ok">row {o.row}: {o.task.id}
            {" "}— {o.task.kind}</div>)}
      </div>}
      {prev && <div className="toolbar" style={{ marginTop: 12 }}>
        <label className="mut small">on conflict
          <select value={conflict} style={{ marginLeft: 6 }}
            onChange={(e) => setConflict(e.target.value)}>
            <option value="skip">skip</option>
            <option value="overwrite">overwrite</option>
            <option value="reject">reject</option>
          </select></label>
        <button className="primary" onClick={apply}
          disabled={prev.bad.length + prev.parse_errors.length > 0 ||
            !prev.ok.length}>
          import {prev.ok.length} task(s)</button>
        {(prev.bad.length + prev.parse_errors.length) > 0 &&
          <span className="mut small">invalid rows block import —
            fix or remove them</span>}
      </div>}
      {msg && <div className="small bad" style={{ marginTop: 8 }}>{msg}</div>}
      <div className="toolbar" style={{ marginTop: 14 }}>
        <button className="link" onClick={onClose}>close</button>
      </div>
    </div>
  </div>;
}

/* ---------- validation panel ---------- */

function ValidationPanel({ report, onOpen }) {
  const [open, setOpen] = useState(false);
  const rows = useMemo(() => {
    if (!report) return [];
    const out = [];
    for (const [tid, iss] of Object.entries(report.tasks || {}))
      for (const i of iss)
        out.push({ ...i, obj: tid, type: "task" });
    for (const [rid, iss] of Object.entries(report.rubrics || {}))
      for (const i of iss)
        out.push({ ...i, obj: rid, type: "rubric" });
    for (const i of report.suites || [])
      out.push({ ...i, obj: i.object, type: "suite" });
    return out;
  }, [report]);
  const errs = rows.filter((r) => r.severity === "error").length;
  const warns = rows.length - errs;
  if (!report) return null;
  return <div className="card" style={{ padding: "10px 18px" }}>
    <div className="toolbar" style={{ marginBottom: 0 }}>
      <b>suite validation</b>
      <span className="pill neg">{errs} error{errs === 1 ? "" : "s"}</span>
      <span className="pill warn">{warns} warning{warns === 1 ? "" : "s"}</span>
      <span className="mut small">
        {Object.values(report.runnable || {}).filter(Boolean).length}/
        {Object.keys(report.runnable || {}).length} tasks runnable</span>
      <button className="link" onClick={() => setOpen(!open)}>
        {open ? "hide" : "show"} details</button>
    </div>
    {open && rows.length > 0 && <div className="iss"
      style={{ marginTop: 10 }}>
      {rows.map((i, k) => <div key={k} className="row">
        <span className={"sev " + i.severity}>{i.severity}</span>
        <button className="link fld-name"
          onClick={() => onOpen(i.type, i.obj)}>{i.obj}</button>
        <span>{i.message}</span>
        {i.fix && <span className="fix">{i.fix}</span>}
      </div>)}
    </div>}
    {open && !rows.length &&
      <div className="small ok" style={{ marginTop: 8 }}>
        suite is clean</div>}
  </div>;
}

/* ---------- page ---------- */

export function SuitePage() {
  const [tasks, setTasks] = useState([]);
  const [rubrics, setRubrics] = useState([]);
  const [suites, setSuites] = useState([]);
  const [report, setReport] = useState(null);
  const [sel, setSel] = useState(null);      // {type, id}
  const [nav, setNav] = useState("tasks");
  const [q, setQ] = useState("");
  const [kindF, setKindF] = useState("");
  const [msg, setMsg] = useState("");
  const [imp, setImp] = useState(false);
  const [newId, setNewId] = useState("");
  const draftDirty = useRef(false);

  const load = () => {
    api("/tasks").then(setTasks).catch(() => {});
    api("/rubrics").then(setRubrics).catch(() => {});
    api("/suites").then(setSuites).catch(() => {});
    api("/suite/validate").then(setReport).catch(() => {});
  };
  useEffect(() => { load(); }, []);

  const open = (type, id) => setSel({ type, id });
  const close = () => setSel(null);
  const refresh = () => load();

  const create = () => {
    const id = newId.trim();
    if (!id) return;
    const url = { tasks: "/tasks", rubrics: "/rubrics",
                  suites: "/suites" }[nav];
    const body = nav === "suites" ? { id, tasks: [] } : { id };
    api(url, { method: "POST", body: JSON.stringify(body) })
      .then(() => { setNewId(""); load(); open(
        nav === "tasks" ? "task" : nav === "rubrics" ? "rubric"
          : "suite", id); })
      .catch((e) => setMsg(String(e)));
  };

  const download = (format) =>
    apiFetch(`/suite/export?format=${format}`).then((r) =>
      r.blob().then((b) => {
        const a = document.createElement("a");
        a.href = URL.createObjectURL(b);
        a.download = `skilllab-tasks.${format}`;
        a.click(); URL.revokeObjectURL(a.href);
      }));

  const tasksF = tasks.filter((t) =>
    (!q || t.id.toLowerCase().includes(q.toLowerCase()) ||
      (t.prompt || "").toLowerCase().includes(q.toLowerCase())) &&
    (!kindF || t.kind === kindF));
  const tIssues = report?.tasks || {};
  const rIssues = report?.rubrics || {};
  const type = sel?.type;

  return <>
    <div className="toolbar" style={{ marginBottom: 14 }}>
      <button className="primary" onClick={() => {
        setNav("tasks"); setSel(null); }}>+ new task</button>
      <button onClick={() => setImp(true)}>import dataset…</button>
      <button onClick={() => download("json")}>export json</button>
      <button onClick={() => download("csv")}>export csv</button>
      <span className="mut small">{msg}</span>
    </div>
    <ValidationPanel report={report} onOpen={(t, id) => {
      setNav(t === "task" ? "tasks" : t === "rubric" ? "rubrics"
        : "suites"); open(t, id); }} />
    <div className="suite" style={{ marginTop: 14 }}>
      <div className="nav-col">
        <div className="nav-tabs">
          {[["tasks", tasks.length], ["rubrics", rubrics.length],
            ["suites", suites.length]].map(([n, c]) =>
            <button key={n} className={nav === n ? "on" : ""}
              onClick={() => { setNav(n); }}>{n} ({c})</button>)}
        </div>
        {nav === "tasks" && <div className="nav-tools">
          <input placeholder="search id / prompt" value={q}
            onChange={(e) => setQ(e.target.value)} />
          <select value={kindF} onChange={(e) => setKindF(e.target.value)}>
            <option value="">all kinds</option>
            {KINDS.map((k) => <option key={k}>{k}</option>)}
          </select>
        </div>}
        <div className="nav-list">
          {nav === "tasks" && <>
            {tasksF.map((t) => <button key={t.id}
              className={"nav-item" +
                (type === "task" && sel.id === t.id ? " on" : "")}
              onClick={() => open("task", t.id)}>
              <Dot issues={tIssues[t.id]} />{t.id}
              <div className="meta">{t.kind}
                {report?.runnable && !report.runnable[t.id] &&
                  " · not runnable"}</div>
            </button>)}
            {!tasksF.length && <div className="ts-empty small">
              {tasks.length ? "no tasks match the filters"
                : "no tasks yet — create your first test case"}</div>}
          </>}
          {nav === "rubrics" && <>
            {rubrics.map((r) => <button key={r.id}
              className={"nav-item" +
                (type === "rubric" && sel.id === r.id ? " on" : "")}
              onClick={() => open("rubric", r.id)}>
              <Dot issues={rIssues[r.id]} />{r.id}
              <div className="meta">
                {(r.criteria || []).length} criteria</div>
            </button>)}
            {!rubrics.length && <div className="ts-empty small">
              no rubrics yet — rubrics score tasks with weighted
              criteria</div>}
          </>}
          {nav === "suites" && <>
            {suites.map((s) => <button key={s.id}
              className={"nav-item" +
                (type === "suite" && sel.id === s.id ? " on" : "")}
              onClick={() => open("suite", s.id)}>
              {s.id}<div className="meta">{s.tasks.length} tasks —
                usable in benchmark "tasks" field</div>
            </button>)}
            {!suites.length && <div className="ts-empty small">
              no named suites — group tasks to run them as a set</div>}
          </>}
        </div>
        {nav !== "suites" || true}
        <div style={{ borderTop: "1px solid var(--rule)",
          display: "flex", gap: 6, padding: "8px 10px" }}>
          <input placeholder={`new ${nav.slice(0, -1)} id`}
            value={newId} style={{ flex: 1, minWidth: 0 }}
            onChange={(e) => setNewId(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && create()} />
          <button onClick={create} disabled={!newId.trim()}>+</button>
        </div>
      </div>
      <div>
        {!sel && <div className="card ts-empty">
          <b>Select a {nav.slice(0, -1)} to edit</b>
          <div className="small" style={{ marginTop: 6 }}>
            tasks define what the agent does and how it is scored ·
            rubrics hold weighted criteria · suites group tasks for
            benchmarks</div>
        </div>}
        {type === "task" &&
          <TaskEditor tid={sel.id} rubrics={rubrics}
            onChanged={refresh}
            onDeleted={(oldId) => { close(); refresh(); }} />}
        {type === "rubric" &&
          <RubricEditor rid={sel.id} onChanged={refresh}
            onDeleted={() => { close(); refresh(); }} />}
        {type === "suite" &&
          <SuiteEditor sid={sel.id} tasks={tasks}
            runnable={report?.runnable}
            onChanged={refresh}
            onDeleted={() => { close(); refresh(); }} />}
      </div>
    </div>
    {imp && <ImportDialog onClose={() => setImp(false)}
      onDone={(m) => { setMsg(m); load(); }} />}
  </>;
}
