"""`lab ui` — static HTML dashboard generated from the lab's file-based core.

No server, no deps: writes ui/ next to lab.yaml; open ui/index.html.
"""

from __future__ import annotations

import html
import json
from pathlib import Path

from .analyzer import analyze_skill
from .lab import Lab
from .models import RunRecord, load_yaml, parse_frontmatter
from .registry import skill_description
from .report import load_runs

_CSS = """
body{font-family:ui-monospace,Menlo,monospace;max-width:1100px;margin:2rem auto;
padding:0 1rem;color:#222;background:#fafafa}
h1{border-bottom:2px solid #333;padding-bottom:.3rem}
h2{margin-top:2rem}
table{border-collapse:collapse;width:100%;margin:1rem 0}
th,td{border:1px solid #ccc;padding:.4rem .6rem;text-align:left;font-size:.9rem}
th{background:#eee}
a{color:#06c}
nav{margin:1rem 0;font-size:.9rem}
pre{background:#f0f0f0;padding:1rem;overflow-x:auto;font-size:.85rem}
.sev-error{color:#b00}.sev-warn{color:#a60}.sev-info{color:#668}
.msg{border:1px solid #ddd;margin:.5rem 0;padding:.5rem .8rem;border-radius:4px}
.role-system{background:#eef}.role-user{background:#efe}
.role-assistant{background:#fff}.role-tool{background:#f6f6f6;color:#555}
.tag{display:inline-block;background:#ddd;border-radius:3px;padding:.1rem .4rem;
font-size:.8rem;margin-right:.3rem}
"""


def _esc(s) -> str:
    return html.escape(str(s))


def _page(lab: Lab, title: str, body: str, depth: int = 0) -> str:
    nav = (f'<nav><a href="{"../" * depth}index.html">index</a> · '
           f'<a href="{"../" * depth}experiments.html">experiments</a> · '
           f'<a href="{"../" * depth}insights.html">insights</a></nav>')
    return (f"<!doctype html><meta charset=utf-8><title>{_esc(title)}</title>"
            f"<style>{_CSS}</style><h1>{_esc(title)}</h1>{nav}{body}")


def _table(headers: list[str], rows: list[list[str]]) -> str:
    th = "".join(f"<th>{_esc(h)}</th>" for h in headers)
    trs = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>"
                  for r in rows)
    return f"<table><tr>{th}</tr>{trs}</table>"


def _skills_section(lab: Lab) -> str:
    rows = []
    for m in lab.skills():
        findings = sum(len(f) for f in analyze_skill(lab, m.id).values())
        desc = ""
        if m.variants:
            desc = skill_description(
                lab.skills_dir / m.id / m.variants[0].path)[:80]
        rows.append([
            f'<a href="skill-{_esc(m.id)}.html">{_esc(m.id)}</a>',
            _esc(m.kind), _esc(m.status),
            _esc(", ".join(v.id for v in m.variants)),
            str(findings), _esc(desc)])
    return ("<h2>Skills</h2>" + _table(
        ["id", "kind", "status", "variants", "findings", "description"], rows))


def _experiments_section(lab: Lab) -> str:
    rows = []
    for d in sorted(lab.experiments_dir.iterdir()):
        ey = d / "experiment.yaml"
        if not ey.is_file():
            continue
        exp = lab.experiment(d.name)
        n_runs = len(load_runs(lab, exp.id))
        rows.append([
            f'<a href="experiments.html#{_esc(exp.id)}">{_esc(exp.id)}</a>',
            _esc(exp.title or exp.hypothesis[:60]), _esc(exp.status),
            str(len(exp.arms)), str(n_runs)])
    return ("<h2>Experiments</h2>" + _table(
        ["id", "title", "status", "arms", "runs"], rows))


def _insights_table(lab: Lab) -> str:
    from .insights import list_insights
    rows = []
    for i in list_insights(lab):
        ev = ", ".join(i["evidence"]) if isinstance(i["evidence"], list) \
            else str(i["evidence"])
        rows.append([_esc(i["kind"]), _esc(i["id"]), _esc(i["status"]),
                     _esc(i["confidence"]), _esc(ev)])
    return _table(["kind", "id", "status", "confidence", "evidence"], rows)


def _transcript_html(tpath: Path) -> str:
    if not tpath.is_file():
        return "<p><i>no transcript</i></p>"
    out = []
    for line in tpath.read_text().splitlines():
        m = json.loads(line)
        role = m.get("role", "?")
        if role == "assistant" and m.get("tool_calls"):
            for tc in m["tool_calls"]:
                out.append(
                    f'<div class="msg role-assistant"><b>assistant → '
                    f'{_esc(tc["function"]["name"])}</b><pre>'
                    f'{_esc(tc["function"]["arguments"])}</pre></div>')
        else:
            name = f" [{m['name']}]" if m.get("name") else ""
            out.append(f'<div class="msg role-{_esc(role)}"><b>{_esc(role)}'
                       f'{_esc(name)}</b><pre>{_esc(m.get("content") or "")}'
                       "</pre></div>")
    return "\n".join(out)


def generate(lab: Lab) -> Path:
    out = lab.d("ui")
    out.mkdir(exist_ok=True)

    # index
    body = (_skills_section(lab) + _experiments_section(lab)
            + "<h2>Insights & principles</h2>" + _insights_table(lab))
    (out / "index.html").write_text(_page(lab, f"Skill Lab — {lab.root.name}",
                                          body))

    # experiments page: one section per experiment with report + run links
    sections = []
    for d in sorted(lab.experiments_dir.iterdir()):
        ey = d / "experiment.yaml"
        if not ey.is_file():
            continue
        exp = lab.experiment(d.name)
        sec = [f'<h2 id="{_esc(exp.id)}">{_esc(exp.id)}</h2>']
        sec.append(f"<p><b>hypothesis:</b> {_esc(exp.hypothesis)}</p>")
        analysis = d / "analysis.md"
        if analysis.is_file():
            sec.append(f"<pre>{_esc(analysis.read_text())}</pre>")
        runs = load_runs(lab, exp.id)
        rows = [[f'<a href="run-{_esc(r.run_id)}.html">{_esc(r.run_id)}</a>',
                 _esc(r.arm), _esc(r.task), _esc(r.status),
                 _esc(r.model.get("name", "")), str(r.usage.turns)]
                for r, _ in runs]
        if rows:
            sec.append(_table(["run", "arm", "task", "status", "model",
                               "turns"], rows))
        sections.append("".join(sec))
    (out / "experiments.html").write_text(
        _page(lab, "Experiments", "".join(sections), 0))

    # run pages (transcripts)
    for d in lab.runs_dir.iterdir() if lab.runs_dir.is_dir() else []:
        if not (d / "run.yaml").is_file():
            continue
        rec = RunRecord(**load_yaml(d / "run.yaml"))
        body = (f"<p><b>experiment:</b> {_esc(rec.experiment)} · "
                f"<b>arm:</b> {_esc(rec.arm)} · <b>task:</b> {_esc(rec.task)}"
                f" · <b>model:</b> {_esc(rec.model.get('name'))} · "
                f"<b>mode:</b> {_esc(rec.injection_mode)}</p>")
        ev = d / "eval.yaml"
        if ev.is_file():
            body += f"<h3>eval</h3><pre>{_esc(ev.read_text())}</pre>"
        body += "<h3>transcript</h3>" + _transcript_html(
            d / "transcript.jsonl")
        (out / f"run-{rec.run_id}.html").write_text(
            _page(lab, rec.run_id, body))

    # skill pages
    for m in lab.skills():
        findings = analyze_skill(lab, m.id)
        rows = []
        for vid, fs in findings.items():
            for f in fs:
                rows.append([_esc(vid), f'<span class="sev-{_esc(f.severity)}">'
                             f"{_esc(f.severity)}</span>", _esc(f.check),
                             _esc(f.message)])
        body = (f"<p><span class=tag>{_esc(m.kind)}</span>"
                f"<span class=tag>{_esc(m.status)}</span></p><h2>Findings</h2>"
                + (_table(["variant", "severity", "check", "message"], rows)
                   if rows else "<p>no findings</p>"))
        for v in m.variants:
            vdir = lab.skills_dir / m.id / v.path
            entry = vdir / "SKILL.md"
            if entry.is_file():
                body += (f"<h2>{_esc(v.id)}</h2>"
                         f"<pre>{_esc(entry.read_text())}</pre>")
        (out / f"skill-{m.id}.html").write_text(
            _page(lab, f"skill: {m.id}", body))

    # insights page: full text of each
    secs = []
    for d in (lab.insights_dir, lab.principles_dir):
        for p in sorted(d.glob("*.md")):
            fm, b = parse_frontmatter(p.read_text())
            secs.append(f"<h2>{_esc(fm.get('id', p.stem))} "
                        f"<small>({d.name})</small></h2>"
                        f"<pre>{_esc(p.read_text())}</pre>")
    (out / "insights.html").write_text(
        _page(lab, "Insights & principles", "".join(secs)))
    return out
