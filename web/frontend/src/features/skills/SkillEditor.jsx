// SkillEditor — in-browser variant workspace.
// Panes: file tree | editor | right rail (info/validate/preview/revisions).
// Saves go through PUT /file with base_sha optimistic concurrency —
// a 409 never discards the user's buffer.
import React, { useEffect, useRef, useState } from "react";
import { api, apiFetch, tok } from "../../api.js";

const SAVE = { clean: "saved", dirty: "unsaved", saving: "saving…",
               saved: "saved", conflict: "conflict", error: "error" };

export function SkillEditor({ skillRef, onClose }) {
  const [files, setFiles] = useState([]);
  const [cur, setCur] = useState(null);      // {path, text, sha, baseText}
  const [state, setState] = useState("clean");
  const [msg, setMsg] = useState("");
  const [tab, setTab] = useState("preview"); // preview|check|revs
  const [revs, setRevs] = useState([]);
  const [revText, setRevText] = useState(null);
  const [check, setCheck] = useState(null);
  const [newFile, setNewFile] = useState("");
  const [meta, setMeta] = useState(null);
  const taRef = useRef(null);

  const dirty = cur && cur.text !== cur.baseText;
  const ref = encodeURIComponent(skillRef);

  /* ---- data ---- */
  const loadFiles = () =>
    api(`/skills/${ref}/files`).then((d) => setFiles(d.files || []))
      .catch((e) => setMsg(String(e)));
  const open = (path) => {
    if (dirty && !window.confirm(
        `Discard unsaved changes to ${cur.path}?`)) return;
    api(`/skills/${ref}/file?path=${encodeURIComponent(path)}`)
      .then((d) => { setCur({ path, text: d.text, baseText: d.text,
                              sha: d.sha });
                     setState("clean"); setRevText(null); })
      .catch((e) => setMsg(String(e)));
  };
  useEffect(() => {
    loadFiles();
    api(`/skills/${ref}/preview`).then(setMeta).catch(() => {});
    api(`/skills/${ref}/check`).then(setCheck).catch(() => setCheck([]));
  }, [skillRef]);
  useEffect(() => {                       // revisions for current file
    if (!cur) return;
    api(`/skills/${ref}/revisions?path=${encodeURIComponent(cur.path)}`)
      .then((d) => setRevs(d.revisions || [])).catch(() => setRevs([]));
  }, [cur?.path, cur?.sha]);

  /* ---- save ---- */
  const save = async () => {
    if (!cur || !dirty) return;
    setState("saving");
    try {
      const r = await api(`/skills/${ref}/file`, { method: "PUT",
        body: JSON.stringify(
          { path: cur.path, text: cur.text, base_sha: cur.sha }) });
      setCur((c) => ({ ...c, sha: r.sha, baseText: c.text }));
      setState("saved"); loadFiles();
    } catch (e) {
      setState(String(e).includes("stale") || e === 409
               ? "conflict" : "error");
      setMsg(String(e));
    }
  };
  const resolveOverwrite = async () => {    // accept our text, new sha
    const d = await api(
      `/skills/${ref}/file?path=${encodeURIComponent(cur.path)}`);
    const r = await api(`/skills/${ref}/file`, { method: "PUT",
      body: JSON.stringify(
        { path: cur.path, text: cur.text, base_sha: d.sha }) });
    setCur((c) => ({ ...c, sha: r.sha, baseText: c.text }));
    setState("saved"); loadFiles();
  };
  const reload = () => open(cur.path);

  /* keyboard: Ctrl/Cmd+S + beforeunload */
  useEffect(() => {
    const kd = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "s") {
        e.preventDefault(); save(); } };
    window.addEventListener("keydown", kd);
    return () => window.removeEventListener("keydown", kd);
  }, [save]);
  useEffect(() => {
    const h = (e) => { if (dirty) { e.preventDefault();
      e.returnValue = ""; } };
    window.addEventListener("beforeunload", h);
    return () => window.removeEventListener("beforeunload", h);
  }, [dirty]);

  /* ---- file ops ---- */
  const createFile = () => {
    const p = newFile.trim();
    if (!p) return;
    api(`/skills/${ref}/file`, { method: "PUT",
      body: JSON.stringify({ path: p, text: "", base_sha: "" }) })
      .then(() => { setNewFile(""); loadFiles(); open(p); })
      .catch((e) => setMsg(String(e)));
  };
  const del = (path) => {
    if (!window.confirm(`Delete ${path}? (snapshot kept in revisions)`))
      return;
    apiFetch(`/skills/${ref}/file?path=${encodeURIComponent(path)}`,
             { method: "DELETE" })
      .then((r) => r.ok ? r.json() : r.json().then((e) =>
        Promise.reject(e.detail)))
      .then(() => { if (cur?.path === path) setCur(null); loadFiles(); })
      .catch((e) => setMsg(String(e)));
  };
  const restore = (rev) => {
    api(`/skills/${ref}/restore`, { method: "POST",
      body: JSON.stringify(
        { path: cur.path, rev, base_sha: cur.sha }) })
      .then((r) => { setMsg(`restored ${rev}`); open(cur.path); })
      .catch((e) => setMsg(String(e)));
  };
  const viewRev = (rev) =>
    api(`/skills/${ref}/revision?path=${encodeURIComponent(cur.path)}` +
        `&rev=${rev}`)
      .then((d) => setRevText(d.text)).catch((e) => setMsg(String(e)));

  const uploadRes = (file) => {
    const fd = new FormData(); fd.append("file", file);
    fetch(`/api/v1/skills/${ref}/resources`, { method: "POST",
      headers: { Authorization: `Bearer ${tok()}` }, body: fd })
      .then((r) => r.ok ? r.json() : r.json().then((e) =>
        Promise.reject(e.detail)))
      .then(() => loadFiles()).catch((e) => setMsg(String(e)));
  };

  /* ---- render ---- */
  const isMd = cur && /\.(md|markdown)$/i.test(cur.path);
  return (
    <div className="editor">
      <div className="ed-head">
        <b>{skillRef}</b>
        <span className="mut small">skill editor</span>
        <span className={`savestate ${state}`}>
          {cur ? SAVE[state] : ""}</span>
        {state === "conflict" && <>
          <span className="small" style={{ color:
            "var(--pill-negative-ink)" }}>file changed on disk</span>
          <button onClick={reload}>Reload</button>
          <button onClick={resolveOverwrite}>Overwrite anyway</button></>}
        <span style={{ flex: 1 }} />
        <button onClick={onClose}>close</button>
      </div>
      {msg && <div className="msg err small">{msg}
        <button className="link" onClick={() => setMsg("")}>×</button>
      </div>}
      <div className="ed-body">
        {/* LEFT — file tree */}
        <div className="ed-tree">
          <div className="ed-tree-head small mut">files</div>
          {files.map((f) => (
            <div key={f.path}
              className={"ed-file" + (cur?.path === f.path
                ? " active" : "")}
              onClick={() => open(f.path)}>
              <span className="fname">{f.path}</span>
              {f.path !== "SKILL.md" &&
                <span className="fop" title="delete"
                  onClick={(e) => { e.stopPropagation(); del(f.path); }}>
                  ×</span>}
            </div>))}
          <div className="ed-new">
            <input value={newFile} placeholder="new file path"
              onChange={(e) => setNewFile(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && createFile()} />
            <button onClick={createFile} disabled={!newFile}>+</button>
          </div>
          <label className="small mut ed-upload">
            <input type="file" style={{ display: "none" }}
              onChange={(e) => e.target.files[0] &&
                uploadRes(e.target.files[0])} />
            + upload resource</label>
        </div>

        {/* CENTER — editor */}
        <div className="ed-main">
          {cur ? <>
            <div className="ed-filebar small">
              <code>{cur.path}</code>
              <span className="mut">sha {cur.sha}</span>
              {dirty && <span className="dirty">● modified</span>}
              <span style={{ flex: 1 }} />
              <button className="primary" disabled={!dirty}
                onClick={save}>Save ⌘S</button>
            </div>
            <div className="ed-wrap">
              <textarea ref={taRef} className="ed-ta" spellCheck="false"
                value={cur.text}
                onChange={(e) => { setCur({ ...cur,
                  text: e.target.value }); setState("dirty"); }} />
            </div>
          </> : <div className="empty mut">select a file to edit —
            SKILL.md is the variant entry point</div>}
        </div>

        {/* RIGHT — rail */}
        <div className="ed-rail">
          <div className="toolbar" style={{ gap: 4 }}>
            {["preview", "check", "revisions"].map((t) =>
              <button key={t}
                className={tab === t ? "primary" : ""}
                onClick={() => setTab(t)}>{t}</button>)}
          </div>
          {tab === "preview" && <div className="ed-pane">
            {meta && <div className="small">
              <div><b>{meta.name || skillRef}</b></div>
              <div className="mut">~{meta.tokens} tok ·
                {meta.entry || "SKILL.md"}</div>
              {(meta.resources || []).length > 0 &&
                <div className="mut">resources:
                  {" "}{meta.resources.join(", ")}</div>}
            </div>}
            {cur ? <pre className="dump ed-md">{revText ?? cur.text}</pre>
                 : <div className="mut small">no file open</div>}
            {revText !== null &&
              <div className="small mut">viewing a revision —
                <button className="link"
                  onClick={() => setRevText(null)}>current</button></div>}
          </div>}
          {tab === "check" && <div className="ed-pane">
            {!check ? <div className="mut small">checking…</div>
             : check.length === 0
               ? <div className="small ok">no findings</div>
               : check.map((f, i) => (
                 <div key={i} className={`finding ${f.severity}`}>
                   <b>{f.severity}</b> {f.id}
                   <div className="small mut">{f.detail}</div>
                 </div>))}
          </div>}
          {tab === "revisions" && <div className="ed-pane">
            {!cur ? <div className="mut small">open a file first</div>
             : revs.length === 0
               ? <div className="mut small">no snapshots yet —
                 revisions appear on every save/delete</div>
               : revs.map((r) => (
                 <div key={r.file} className="rev-row small">
                   <code>{r.rev}</code>
                   <span className="mut">{r.bytes}b</span>
                   <button className="link"
                     onClick={() => viewRev(r.rev)}>view</button>
                   <button className="link"
                     onClick={() => restore(r.rev)}>restore</button>
                 </div>))}
          </div>}
        </div>
      </div>
    </div>);
}
