// ExperimentBuilder — visual editor for experiment.yaml.
// Structured forms only — users never touch YAML. Server-side
// validation runs on save AND before run (preflight + job queue).
import React, { useEffect, useState } from "react";
import { api } from "../../api.js";

const CATS = ["capability","trigger","workflow","instruction","resource",
  "tool-use","compatibility","reliability","efficiency"];
const IVARS = ["skill_variant","model","injection_mode","harness"];
const MODES = ["available","injected"];

export function ExperimentBuilder({ eid, onClose, onRan }) {
  const [exp, setExp] = useState(null);
  const [tasks, setTasks] = useState([]);
  const [skills, setSkills] = useState([]);
  const [msg, setMsg] = useState("");
  const [verdict, setVerdict] = useState(null);  // {valid,errors,warnings}
  const [job, setJob] = useState(null);
  const [runs, setRuns] = useState([]);

  const load = () => api(`/experiments/${eid}`)
    .then((d) => { setExp(d.experiment); }).catch((e) => setMsg(String(e)));
  useEffect(() => {
    load();
    api("/tasks").then(setTasks).catch(() => {});
    api("/skills").then(setSkills).catch(() => {});
    api(`/experiments/${eid}/runs`).then((rs) =>
      setRuns(rs.map((r) => r.run.run_id || r.run.id))).catch(() => {});
  }, [eid]);

  /* job progress polling — real counts from the worker */
  useEffect(() => {
    if (!job || !["queued","running"].includes(job.status)) return;
    const t = setInterval(() =>
      api(`/jobs/${job.id}`).then(setJob).catch(() => {}), 900);
    return () => clearInterval(t);
  }, [job?.id, job?.status]);

  if (!exp) return <div className="mut">loading experiment…</div>;
  const set = (k, v) => setExp({ ...exp, [k]: v });
  const setFx = (k, v) =>
    setExp({ ...exp, fixed: { ...exp.fixed, [k]: v } });
  const concluded = exp.status === "concluded";

  const save = () =>
    api(`/experiments/${eid}/config`, { method: "PUT",
      body: JSON.stringify(exp) })
      .then((v) => { setVerdict(v);
        setMsg(v.valid ? "saved" : `saved — ${v.errors.length} error(s)`); })
      .catch((e) => setMsg(String(e)));
  const validate = () =>
    api(`/experiments/${eid}/validate`).then(setVerdict)
      .catch((e) => setMsg(String(e)));
  const run = () =>
    api(`/experiments/${eid}/run`, { method: "POST" })
      .then((r) => { setJob({ id: r.job, status: "queued" });
        setMsg(`job ${r.job} — ${r.planned} rollouts planned`); })
      .catch((e) => setMsg(String(e)));

  /* ---- arms ---- */
  const setArm = (i, k, v) => {
    const arms = exp.arms.slice();
    arms[i] = { ...arms[i], [k]: v || null };
    setExp({ ...exp, arms });
  };
  const skillOpts = [];
  skills.forEach((s) => (s.variants || []).forEach((v) =>
    skillOpts.push(`${s.id}@${v.id}`)));

  return (
    <div className="expb">
      <div className="ed-head">
        <b>{exp.id}</b>
        <span className={`pill ${exp.status}`}>{exp.status}</span>
        {concluded &&
          <span className="small mut">concluded — read-only</span>}
        <span style={{ flex: 1 }} />
        {!concluded && <>
          <button className="primary" onClick={save}>Save</button>
          <button onClick={validate}>Validate</button>
          <button onClick={run}
            disabled={verdict && !verdict.valid}>Run</button></>}
        <button onClick={onClose}>close</button>
      </div>
      {msg && <div className="msg err small">{msg}
        <button className="link" onClick={() => setMsg("")}>×</button>
      </div>}

      <div className="expb-grid">
        <div className="card">
          <h3>General</h3>
          <label className="fld">title
            <input value={exp.title || ""} disabled={concluded}
              onChange={(e) => set("title", e.target.value)} /></label>
          <label className="fld">hypothesis
            <textarea rows={2} value={exp.hypothesis || ""}
              disabled={concluded}
              onChange={(e) => set("hypothesis", e.target.value)} /></label>
          <div className="fldrow">
            <label className="fld">category
              <select value={exp.category || "trigger"}
                disabled={concluded}
                onChange={(e) => set("category", e.target.value)}>
                {CATS.map((c) => <option key={c}>{c}</option>)}
              </select></label>
            <label className="fld">independent variable
              <select value={exp.independent_var} disabled={concluded}
                onChange={(e) => set("independent_var", e.target.value)}>
                {IVARS.map((c) => <option key={c}>{c}</option>)}
              </select></label>
          </div>
        </div>

        <div className="card">
          <h3>Model & execution</h3>
          <div className="fldrow">
            <label className="fld">model
              <input value={exp.fixed.model} disabled={concluded}
                onChange={(e) => setFx("model", e.target.value)} /></label>
            <label className="fld">temperature (0–2)
              <input type="number" step="0.1" min="0" max="2"
                value={exp.fixed.temperature} disabled={concluded}
                onChange={(e) =>
                  setFx("temperature", parseFloat(e.target.value)||0)} /></label>
          </div>
          <div className="fldrow">
            <label className="fld">injection mode
              <select value={exp.fixed.injection_mode} disabled={concluded}
                onChange={(e) => setFx("injection_mode", e.target.value)}>
                {MODES.map((c) => <option key={c}>{c}</option>)}
              </select></label>
            <label className="fld">rollouts / arm
              <input type="number" min="1" max="20"
                value={exp.rollouts_per_arm} disabled={concluded}
                onChange={(e) => set("rollouts_per_arm",
                  parseInt(e.target.value, 10) || 1)} /></label>
          </div>
        </div>

        <div className="card">
          <h3>Arms <span className="mut small">
            control has no skill — treatment injects/loads it</span></h3>
          {exp.arms.map((a, i) => (
            <div key={i} className="arm-row">
              <input value={a.name} disabled={concluded}
                placeholder="arm name"
                onChange={(e) => setArm(i, "name", e.target.value)} />
              <select value={a.skill || ""} disabled={concluded}
                onChange={(e) => setArm(i, "skill", e.target.value)}>
                <option value="">— control (no skill) —</option>
                {skillOpts.map((s) => <option key={s}>{s}</option>)}
              </select>
              {exp.independent_var === "model" &&
                <input value={a.model || ""} placeholder="model"
                  disabled={concluded}
                  onChange={(e) => setArm(i, "model", e.target.value)} />}
              {exp.independent_var === "injection_mode" &&
                <select value={a.injection_mode || ""} disabled={concluded}
                  onChange={(e) =>
                    setArm(i, "injection_mode", e.target.value)}>
                  <option value="">fixed mode</option>
                  {MODES.map((m) => <option key={m}>{m}</option>)}
                </select>}
              {!concluded && <button className="link"
                onClick={() => setExp({ ...exp,
                  arms: exp.arms.filter((_, j) => j !== i) })}>×</button>}
            </div>))}
          {!concluded && <button onClick={() => setExp({ ...exp,
            arms: [...exp.arms,
              { name: `arm-${exp.arms.length + 1}`, skill: null }] })}>
            + arm</button>}
        </div>

        <div className="card">
          <h3>Tasks <span className="mut small">
            {exp.tasks.length} selected</span></h3>
          <div className="task-pick">
            {tasks.map((t) => {
              const on = exp.tasks.includes(t.id);
              return (
                <label key={t.id} className={"task-chip" +
                  (on ? " on" : "")}>
                  <input type="checkbox" checked={on}
                    disabled={concluded}
                    onChange={() => set("tasks", on
                      ? exp.tasks.filter((x) => x !== t.id)
                      : [...exp.tasks, t.id])} />
                  <span className="tid">{t.id}</span>
                  <span className="mut">{t.kind}</span>
                </label>);
            })}
          </div>
        </div>
      </div>

      {verdict && <div className="card">
        <h3>Validation <span className={verdict.valid ? "ok" : "bad"}>
          {verdict.valid ? "valid" : "invalid"}</span></h3>
        {(verdict.errors || []).map((e, i) =>
          <div key={i} className="small bad">✗ {e}</div>)}
        {(verdict.warnings || []).map((w, i) =>
          <div key={i} className="small mut">⚠ {w}</div>)}
      </div>}

      {job && <div className="card">
        <h3>Execution · {job.id} <span className={`pill ${job.status}`}>
          {job.status}</span></h3>
        <div className="prog">
          <div className="prog-bar"
            style={{ width: `${(job.progress || 0) * 100}%` }} /></div>
        <div className="small mut">{job.operation || ""} —{" "}
          {Math.round((job.progress || 0) * 100)}%</div>
        {(job.logs || []).slice(-8).map((ln, i) =>
          <div key={i} className="small mut mono">{ln}</div>)}
        {job.error && <div className="small bad">{job.error}</div>}
        {job.status === "completed" &&
          <button onClick={onRan}>View results →</button>}
      </div>}

      {runs.length > 0 && <div className="card">
        <h3>Runs ({runs.length})</h3>
        <div className="small mut mono" style={{ maxHeight: 140,
          overflowY: "auto" }}>
          {runs.map((r) => <div key={r}><a href={`/runs/${r}`}>{r}</a>
          </div>)}
        </div>
      </div>}
    </div>);
}
