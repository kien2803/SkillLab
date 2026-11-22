import { useEffect, useRef, useState } from "react";
import { useInView, animate } from "motion/react";

/* Representative product previews for the landing page. These mirror the
   workbench's real UI language (mono data, row tables, verdict pills).
   All figures are sample data, labelled as such on the page. */

function Num({ to, decimals = 2, prefix = "", style }) {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true, margin: "-10%" });
  const [v, setV] = useState(0);
  useEffect(() => {
    if (!inView) return;
    const c = animate(0, to, { duration: 1.1,
      ease: [0.16, 1, 0.3, 1], onUpdate: setV });
    return () => c.stop();
  }, [inView, to]);
  const s = v.toFixed(decimals);
  return <div ref={ref} className="num" style={style}>
    {prefix}{to < 0 ? s.replace("-", "−") : s}</div>;
}

function UI({ title, children, sample = true }) {
  return <div className="lp-ui">
    <div className="lp-ui-bar"><i /><i /><i /><span>{title}</span></div>
    {sample && <span className="sample">sample data</span>}
    <div className="lp-ui-body">{children}</div>
  </div>;
}

export function HeroPreview() {
  return <UI title="skilllab · benchmark — commit-helper@v3-bp">
    <div className="lp-mgrid">
      <div className="lp-metric">
        <Num to={0.41} prefix="+" style={{ color: "var(--lp-ok)" }} />
        <div className="cap">Δ score vs control</div></div>
      <div className="lp-metric">
        <Num to={0.83} />
        <div className="cap">treatment mean</div></div>
      <div className="lp-metric">
        <Num to={0.42} />
        <div className="cap">control mean</div></div>
    </div>
    <table className="lp-t">
      <thead><tr><th>task</th><th className="n">control</th>
        <th className="n">with skill</th><th className="n">Δ</th></tr></thead>
      <tbody>
        <tr className="imp"><td className="task">write-commit</td>
          <td className="n">0.44</td><td className="n">0.86</td>
          <td className="n"><span className="lp-delta up">+0.42</span></td></tr>
        <tr className="imp"><td className="task">summarize-diff</td>
          <td className="n">0.51</td><td className="n">0.81</td>
          <td className="n"><span className="lp-delta up">+0.30</span></td></tr>
        <tr className="reg"><td className="task">fix-typo</td>
          <td className="n">0.62</td><td className="n">0.48</td>
          <td className="n"><span className="lp-delta dn">−0.14</span></td></tr>
      </tbody>
    </table>
  </UI>;
}

export function SkillPreview() {
  return <UI title="skill editor — commit-helper@v3-bp">
    <div className="lp-tree">
      <div><b>commit-helper</b> <span className="lp-tag line">v3-bp</span></div>
      <div>├─ <span className="sel">SKILL.md</span> <span style={{ color: "var(--lp-faint)" }}>412 tok</span></div>
      <div>├─ resources/</div>
      <div>│&nbsp;&nbsp;└─ examples.md</div>
      <div>└─ revisions/ <span style={{ color: "var(--lp-faint)" }}>r007 · r008 · r009</span></div>
      <div style={{ marginTop: 8 }}>
        <span className="lp-tag ok">check: clean</span>{" "}
        <span className="lp-tag line">immutable variant</span></div>
    </div>
  </UI>;
}

export function SuitePreview() {
  return <UI title="test suite — commit-tasks · 4 cases">
    <table className="lp-t">
      <thead><tr><th>task</th><th>kind</th><th>rubric</th></tr></thead>
      <tbody>
        <tr><td className="task">write-commit</td><td>performance</td><td>commit-rubric</td></tr>
        <tr><td className="task">summarize-diff</td><td>performance</td><td>commit-rubric</td></tr>
        <tr><td className="task">trigger-commit</td><td>trigger</td><td>trigger-rubric</td></tr>
        <tr><td className="task">unrelated-task</td><td>negative</td><td>trigger-rubric</td></tr>
      </tbody>
    </table>
  </UI>;
}

export function RegressionPreview() {
  return <UI title="regression — v1 → v3-bp">
    <div className="lp-krow"><span className="k">verdict</span>
      <span className="v"><span className="lp-tag ok">clean</span></span></div>
    <div className="lp-krow"><span className="k">critical</span>
      <span className="v">0 findings</span></div>
    <div className="lp-krow"><span className="k">quality</span>
      <span className="v">2 improved · 0 regressed</span></div>
    <div className="lp-krow"><span className="k">activation</span>
      <span className="v">83% · threshold 80%</span></div>
    <div className="lp-krow"><span className="k">candidate hash</span>
      <span className="v mono" style={{ fontSize: 11 }}>845032…</span></div>
  </UI>;
}

export function ReportPreview() {
  return <UI title="quality report — commit-helper@v3-bp">
    <div className="lp-krow"><span className="k">verdict</span>
      <span className="v" style={{ color: "var(--lp-ok)" }}>improved</span></div>
    <div className="lp-krow"><span className="k">evidence</span>
      <span className="v">hash-pinned · 53 runs</span></div>
    <div className="lp-krow"><span className="k">checklist</span>
      <span className="v">✓ static · ✓ evals · ✓ regression</span></div>
    <div className="lp-krow"><span className="k">export</span>
      <span className="v">report.md</span></div>
  </UI>;
}

export function Showcase() {
  return <UI title="skilllab · quality report — commit-helper@v3-bp">
    <div className="lp-dash-top">
      <span className="who">baseline: no skill · candidate: v3-bp ·
        model: mock · rollouts: 4/task</span>
      <span className="lp-verdict">✓ improved</span>
    </div>
    <div className="lp-mgrid">
      <div className="lp-metric"><Num to={0.83} />
        <div className="cap">success, with skill</div></div>
      <div className="lp-metric"><Num to={0.42} />
        <div className="cap">success, baseline</div></div>
      <div className="lp-metric"><Num to={0.41} prefix="+"
        style={{ color: "var(--lp-ok)" }} />
        <div className="cap">Δ correctness</div></div>
    </div>
    <div className="lp-cols2">
      <div className="lp-panel">
        <h4>score matrix — arm × task</h4>
        <table className="lp-t">
          <thead><tr><th>task</th><th className="n">control</th>
            <th className="n">v3-bp</th><th className="n">Δ</th>
            <th>status</th></tr></thead>
          <tbody>
            <tr className="imp"><td className="task">write-commit</td>
              <td className="n">0.44</td><td className="n">0.86</td>
              <td className="n"><span className="lp-delta up">+0.42</span></td>
              <td><span className="lp-tag ok">improved</span></td></tr>
            <tr className="imp"><td className="task">summarize-diff</td>
              <td className="n">0.51</td><td className="n">0.81</td>
              <td className="n"><span className="lp-delta up">+0.30</span></td>
              <td><span className="lp-tag ok">improved</span></td></tr>
            <tr className="reg"><td className="task">fix-typo</td>
              <td className="n">0.62</td><td className="n">0.48</td>
              <td className="n"><span className="lp-delta dn">−0.14</span></td>
              <td><span className="lp-tag bad">regressed</span></td></tr>
            <tr><td className="task">trigger-commit</td>
              <td className="n">0.10</td><td className="n">0.83</td>
              <td className="n"><span className="lp-delta up">+0.73</span></td>
              <td><span className="lp-tag ok">improved</span></td></tr>
          </tbody>
        </table>
      </div>
      <div>
        <div className="lp-panel" style={{ marginBottom: 16 }}>
          <h4>release checklist</h4>
          <div className="lp-krow"><span className="k">static analysis</span>
            <span className="v" style={{ color: "var(--lp-ok)" }}>✓ clean</span></div>
          <div className="lp-krow"><span className="k">exact-hash eval</span>
            <span className="v" style={{ color: "var(--lp-ok)" }}>✓ passed</span></div>
          <div className="lp-krow"><span className="k">regression suite</span>
            <span className="v" style={{ color: "var(--lp-ok)" }}>✓ clean</span></div>
          <div className="lp-krow"><span className="k">content hash</span>
            <span className="v mono" style={{ fontSize: 11 }}>sha256:845032…</span></div>
        </div>
        <div className="lp-panel">
          <h4>run inspection — fix-typo</h4>
          <div className="lp-krow"><span className="k">status</span>
            <span className="v"><span className="lp-tag bad">failed</span></span></div>
          <div className="lp-krow"><span className="k">first failure</span>
            <span className="v">instruction-drift</span></div>
          <div className="lp-krow"><span className="k">eval</span>
            <span className="v">0.48 / rubric commit-rubric</span></div>
          <div className="lp-krow"><span className="k">evidence</span>
            <span className="v">transcript · artifacts</span></div>
        </div>
      </div>
    </div>
  </UI>;
}
