import React, { useEffect, useState } from "react";
const api = (p) => fetch("/api/v1" + p).then((r) => r.json());
export default function App() {
  const [projects, setProjects] = useState([]);
  const [skills, setSkills] = useState([]);
  const [err, setErr] = useState("");
  useEffect(() => {
    Promise.all([api("/projects"), api("/skills")])
      .then(([p, s]) => { setProjects(p); setSkills(s); })
      .catch((e) => setErr(String(e)));
  }, []);
  return (
    <main style={{ fontFamily: "monospace", padding: 24 }}>
      <h1>SkillLab</h1>
      {err && <p style={{ color: "red" }}>{err}</p>}
      <h2>Research Projects</h2>
      <ul>{projects.map((p) => (
        <li key={p.id}><b>{p.id}</b> — {p.title} [{p.status}]</li>))}
      </ul>
      <h2>Skills</h2>
      <ul>{skills.map((s) => (
        <li key={s.id}><b>{s.id}</b> — {s.variants.length} variant(s)</li>))}
      </ul>
    </main>
  );
}
