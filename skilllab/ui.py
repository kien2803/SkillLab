"""`lab ui` — static HTML dashboard generated from the lab's file-based core.

No server, no deps, no external assets: writes ui/ next to lab.yaml; open
ui/index.html. All numbers come from run.yaml/eval.yaml/regression records —
nothing is fabricated, and mock-model data is labelled as simulated.
"""

from __future__ import annotations

import html
import json
import statistics
from datetime import datetime
from pathlib import Path

from .analyzer import analyze_skill
from .lab import Lab
from .models import (EvalResult, RunRecord, load_yaml, parse_frontmatter,
                     parse_skill_ref)
from .registry import skill_description
from .report import load_runs
from . import research
from . import blueprint

_CSS = """
:root{--bg:#eef0f3;--panel:#ffffff;--panel2:#f4f6f8;--border:#dde1e7;
--text:#0b0c0e;--muted:#5d6470;--accent:#1f2de6;--ok:#1d7a46;--bad:#9a2828;
--warn:#6d4e0c;--info:#1f2de6;--purple:#6d4fc2;
--font:"Familjen Grotesk",system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
--mono:"IBM Plex Mono",ui-monospace,"SFMono-Regular",Menlo,Consolas,monospace}
*{box-sizing:border-box}
body{font-family:var(--font);margin:0;background:var(--bg);color:var(--text);
font-size:14px;line-height:1.5}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}
.topbar{display:flex;align-items:center;gap:1.2rem;padding:.7rem 1.4rem;
background:var(--panel);border-bottom:1px solid var(--border);
position:sticky;top:0;z-index:10}
.topbar .brand{display:inline-flex;align-items:center;gap:.5rem;
font-weight:600;color:var(--text);font-size:1.05rem;letter-spacing:-.01em}
.topbar .brand::before{content:"S";display:inline-flex;align-items:center;
justify-content:center;width:22px;height:22px;border-radius:5px;
background:var(--accent);color:#fff;font:600 13px/1 var(--mono)}
.topbar nav{display:flex;gap:.2rem;flex-wrap:wrap}
.topbar nav a{color:var(--muted);padding:.3rem .7rem;border-radius:5px;
font-size:.88rem}
.topbar nav a:hover{background:var(--panel2);color:var(--text);text-decoration:none}
.topbar nav a.active{background:rgb(31 45 230/.08);color:var(--accent);font-weight:600}
.wrap{max-width:1280px;margin:0 auto;padding:1.4rem}
h1{font-size:1.5rem;margin:.2rem 0 1rem;letter-spacing:-.02em}
h2{font-size:1.15rem;margin:1.8rem 0 .6rem;color:var(--text);
letter-spacing:-.02em}
h3{font:500 .78rem/1.4 var(--mono);margin:1.2rem 0 .4rem;color:var(--muted);
text-transform:uppercase;letter-spacing:.06em}
.grid{display:grid;gap:.9rem}
.cards{grid-template-columns:repeat(auto-fit,minmax(150px,1fr))}
.card{background:var(--panel);border:1px solid var(--border);border-radius:6px;
padding:.9rem 1rem;box-shadow:0 1px 2px rgb(11 12 14/.04)}
.card .num{font-size:1.7rem;font-weight:600;line-height:1.1;
letter-spacing:-.02em;font-variant-numeric:tabular-nums}
.card .lbl{color:var(--muted);font:500 .72rem/1.3 var(--mono);
text-transform:uppercase;letter-spacing:.06em}
.card .sub{color:var(--muted);font-size:.78rem;margin-top:.15rem}
.card.bad .num{color:var(--bad)}.card.ok .num{color:var(--ok)}
.card.warn .num{color:var(--warn)}
table{border-collapse:collapse;width:100%;margin:.6rem 0;font-size:.86rem}
th,td{padding:.5rem .7rem;text-align:left;border-bottom:1px solid var(--border)}
th{color:var(--muted);font:500 .72rem/1.3 var(--mono);text-transform:uppercase;
letter-spacing:.06em;background:var(--panel);position:sticky;top:48px}
table.sortable th{cursor:pointer;user-select:none}
table.sortable th:hover{color:var(--text)}
table.sortable th.sorted-asc::after{content:" ▲";font-size:.6rem}
table.sortable th.sorted-desc::after{content:" ▼";font-size:.6rem}
tr:hover td{background:var(--panel2)}
.num-cell{font-variant-numeric:tabular-nums;text-align:right}
.badge{display:inline-block;padding:.15rem .6rem;border-radius:99px;
font:500 .74rem/1.3 var(--mono);letter-spacing:.01em}
.b-ok{background:rgb(29 122 70/.10);color:var(--ok)}
.b-bad{background:rgb(154 40 40/.10);color:var(--bad)}
.b-warn{background:rgb(109 78 12/.12);color:var(--warn)}
.b-info{background:rgb(31 45 230/.09);color:var(--info)}
.b-purple{background:rgb(109 79 194/.10);color:var(--purple)}
.b-muted{background:var(--bg);color:var(--muted)}
.muted{color:var(--muted)}
.empty{border:1px dashed var(--border);border-radius:6px;padding:1.6rem;
text-align:center;color:var(--muted);margin:.8rem 0}
.note{border-left:3px solid var(--warn);background:rgb(109 78 12/.06);
padding:.6rem .9rem;border-radius:0 6px 6px 0;margin:.8rem 0;font-size:.85rem}
.note.info{border-color:var(--info);background:rgb(31 45 230/.06)}
.note.err{border-color:var(--bad);background:rgb(154 40 40/.06)}
.bar-row{display:flex;align-items:center;gap:.6rem;margin:.28rem 0}
.bar-row .bar-lbl{width:180px;font-size:.82rem;overflow:hidden;
text-overflow:ellipsis;white-space:nowrap;flex-shrink:0}
.bar-track{flex:1;background:#e2e5ea;border-radius:4px;height:16px;
overflow:hidden}
.bar-fill{height:100%;border-radius:4px;background:var(--accent);
min-width:2px}
.bar-fill.ok{background:var(--ok)}.bar-fill.bad{background:var(--bad)}
.bar-fill.warn{background:var(--warn)}.bar-fill.purple{background:var(--purple)}
.bar-val{width:64px;text-align:right;font-size:.8rem;
font-variant-numeric:tabular-nums;flex-shrink:0}
.msg{border:1px solid var(--border);border-radius:6px;margin:.4rem 0;
padding:.5rem .8rem;background:var(--panel)}
.msg pre{margin:.3rem 0 0;white-space:pre-wrap;word-break:break-word;
font:400 .78rem/1.5 var(--mono);color:var(--muted)}
.role-system{border-left:3px solid var(--purple)}
.role-user{border-left:3px solid var(--info)}
.role-assistant{border-left:3px solid var(--ok)}
.role-tool{border-left:3px solid var(--border);background:var(--panel2)}
.role-badge{font:500 .7rem/1.3 var(--mono);text-transform:uppercase;
letter-spacing:.06em;color:var(--muted)}
.filter{width:100%;max-width:340px;background:var(--panel);
border:1px solid var(--border);border-radius:6px;color:var(--text);
padding:.45rem .7rem;font-size:.85rem;margin:.3rem 0}
.filter:focus{outline:2px solid rgb(31 45 230/.4);outline-offset:1px;
border-color:var(--accent)}
.section{background:var(--panel);border:1px solid var(--border);
border-radius:6px;padding:1rem 1.2rem;margin:.9rem 0;
box-shadow:0 1px 2px rgb(11 12 14/.04)}
details{margin:.4rem 0}
summary{cursor:pointer;color:var(--accent);font-size:.85rem}
pre.raw{background:var(--panel2);border:1px solid var(--border);
border-radius:6px;padding:.8rem;overflow-x:auto;
font:400 .78rem/1.55 var(--mono);
color:var(--muted);max-height:420px;overflow-y:auto}
code{font-family:var(--mono);font-size:.9em}
.two-col{display:grid;grid-template-columns:1fr 1fr;gap:.9rem}
@media(max-width:900px){.two-col{grid-template-columns:1fr}
.bar-row .bar-lbl{width:110px}}
@media(max-width:640px){.topbar{flex-wrap:wrap}.wrap{padding:.8rem}
th,td{padding:.4rem}}
"""

_JS = r"""
function sortTable(th){
  const t=th.closest('table'),tb=t.tBodies[0],idx=th.cellIndex;
  const asc=!th.classList.contains('sorted-asc');
  t.querySelectorAll('th').forEach(h=>h.classList.remove('sorted-asc','sorted-desc'));
  th.classList.add(asc?'sorted-asc':'sorted-desc');
  [...tb.rows].sort((a,b)=>{
    const x=a.cells[idx]?.dataset.v??a.cells[idx]?.innerText??'';
    const y=b.cells[idx]?.dataset.v??b.cells[idx]?.innerText??'';
    const nx=parseFloat(x),ny=parseFloat(y);
    if(!isNaN(nx)&&!isNaN(ny))return asc?nx-ny:ny-nx;
    return asc?String(x).localeCompare(y):String(y).localeCompare(x);
  }).forEach(r=>tb.appendChild(r));
}
document.querySelectorAll('table.sortable th').forEach(th=>
  th.addEventListener('click',()=>sortTable(th)));
document.querySelectorAll('input.filter').forEach(inp=>{
  const sel=inp.dataset.target;inp.addEventListener('input',()=>{
    const q=inp.value.toLowerCase();
    document.querySelectorAll(sel+' [data-frow]').forEach(r=>{
      r.style.display=r.innerText.toLowerCase().includes(q)?'':'none';
    });
  });
});
"""


def _esc(s) -> str:
    return html.escape(str(s), quote=True)


def _fmt(x: float | None, pct: bool = False) -> str:
    if x is None:
        return "—"
    return f"{x:.0%}" if pct else f"{x:.2f}"


def _badge(text: str, kind: str = "muted") -> str:
    return f'<span class="badge b-{kind}">{_esc(text)}</span>'


_STATUS_BADGE = {
    "ok": "ok", "passed": "ok", "clean": "ok", "graduated": "ok",
    "confirmed": "ok", "promoted": "ok",
    "failed": "bad", "error": "bad", "regressed": "bad",
    "refuted": "bad",
    "pending": "warn", "candidate": "warn", "designed": "warn",
    "inconclusive": "warn",
    "running": "info", "analyzed": "info", "testing": "info",
    "concluded": "purple",
}


def _sbadge(status: str | None) -> str:
    s = status or "missing"
    return _badge(s, _STATUS_BADGE.get(s, "muted"))


def _empty(msg: str) -> str:
    return f'<div class="empty">{_esc(msg)}</div>'


def _nav(active: str, depth: int = 0) -> str:
    pre = "../" * depth
    items = [("index", "Overview"), ("research", "Research"),
             ("skills", "Skills"),
             ("benchmarks", "Benchmarks"), ("regressions", "Regressions"),
             ("experiments", "Experiments"), ("insights", "Knowledge")]
    links = "".join(
        f'<a href="{pre}{k}.html" class="{"active" if k == active else ""}">'
        f'{v}</a>' for k, v in items)
    return (f'<div class="topbar"><span class="brand">SkillLab</span>'
            f"<nav>{links}</nav></div>")


def _page(lab: Lab, title: str, body: str, active: str = "index",
          depth: int = 0) -> str:
    return (f"<!doctype html><html lang=en><meta charset=utf-8>"
            f'<meta name="viewport" content="width=device-width,'
            f' initial-scale=1"><title>{_esc(title)} — SkillLab</title>'
            f'<link rel="preconnect" href="https://fonts.googleapis.com">'
            f'<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
            f'<link href="https://fonts.googleapis.com/css2?family=Familjen+Grotesk'
            f':wght@400..700&family=IBM+Plex+Mono:wght@400;500&display=swap"'
            f' rel="stylesheet">'
            f"<style>{_CSS}</style>{_nav(active, depth)}"
            f'<div class="wrap"><h1>{_esc(title)}</h1>{body}</div>'
            f"<script>{_JS}</script>")


def _table(headers: list[str], rows: list[list[str]],
           sortable: bool = True, table_id: str | None = None) -> str:
    cls = "sortable" if sortable else ""
    tid = f' id="{_esc(table_id)}"' if table_id else ""
    th = "".join(f"<th>{_esc(h)}</th>" for h in headers)
    trs = "".join("<tr data-frow>" + "".join(f"<td>{c}</td>" for c in r)
                  + "</tr>" for r in rows)
    return f'<table class="{cls}"{tid}><thead><tr>{th}</tr></thead>' \
           f"<tbody>{trs}</tbody></table>"


def _filter(target: str, placeholder: str = "filter rows…") -> str:
    return (f'<input class="filter" data-target="#{_esc(target)}" '
            f'placeholder="{_esc(placeholder)}">')


def _bar(label: str, value: float, maxv: float = 1.0,
         cls: str = "") -> str:
    pct = max(0.0, min(1.0, value / maxv if maxv else 0.0)) * 100
    return (f'<div class="bar-row"><span class="bar-lbl">{_esc(label)}</span>'
            f'<div class="bar-track"><div class="bar-fill {cls}" '
            f'style="width:{pct:.1f}%"></div></div>'
            f'<span class="bar-val">{value:.2f}</span></div>')


def _stat(label: str, value, cls: str = "", sub: str = "") -> str:
    s = f'<div class="sub">{sub}</div>' if sub else ""
    return (f'<div class="card {cls}"><div class="num">{value}</div>'
            f'<div class="lbl">{_esc(label)}</div>{s}</div>')


def _duration(rec: RunRecord) -> float | None:
    try:
        return (datetime.fromisoformat(rec.finished)
                - datetime.fromisoformat(rec.started)).total_seconds()
    except (ValueError, TypeError):
        return None


def _is_mock(rec: RunRecord) -> bool:
    return str(rec.model.get("name", "")).startswith("mock")


def _mock_note(runs: list[tuple[RunRecord, EvalResult | None]]) -> str:
    if runs and all(_is_mock(r) for r, _ in runs):
        return ('<div class="note">All runs on this page use the '
                '<b>mock</b> model — data is simulated, not real-world '
                "model performance.</div>")
    return ""


def _all_runs(lab: Lab) -> list[tuple[RunRecord, EvalResult | None]]:
    out = []
    if not lab.runs_dir.is_dir():
        return out
    for d in sorted(lab.runs_dir.iterdir()):
        ry = d / "run.yaml"
        if not ry.is_file():
            continue
        try:
            rec = RunRecord(**load_yaml(ry))
        except Exception:
            continue
        ey = d / "eval.yaml"
        ev = None
        if ey.is_file():
            try:
                ev = EvalResult(**load_yaml(ey))
            except Exception:
                ev = None
        out.append((rec, ev))
    return out


def _stats(rows: list[tuple[RunRecord, EvalResult | None]],
           skill_id: str | None = None) -> dict:
    ok = [(r, e) for r, e in rows if r.status == "ok"]
    finals = [e for _, e in ok
              if e is not None and e.status in ("passed", "failed")]
    scores = [
        e.rubric_score if e.rubric_score is not None
        else (1.0 if e.status == "passed" else 0.0)
        for e in finals
    ]
    toks = [r.usage.input_tokens + r.usage.output_tokens for r, _ in ok]
    durs = [d for r, _ in ok if (d := _duration(r)) is not None]
    acts = []
    if skill_id:
        acts = [1.0 if r.activated(skill_id) else 0.0 for r, _ in ok]
    m = statistics.mean
    return {
        "n": len(rows), "errors": sum(1 for r, _ in rows
                                      if r.status == "error"),
        "incomplete": len(ok) - len(finals),
        "success": (sum(1 for e in finals if e.status == "passed")
                    / len(finals)) if finals else None,
        "score": m(scores) if scores else None,
        "activated": m(acts) if acts else None,
        "tokens": m(toks) if toks else None,
        "latency": m(durs) if durs else None,
        "turns": m([r.usage.turns for r, _ in ok]) if ok else None,
        "variance": statistics.pstdev(scores) if len(scores) > 1 else 0.0,
    }


# ------------------------------------------------------------ page: overview


def _overview(lab: Lab, runs, regs) -> str:
    n_fail = sum(1 for r, _ in runs if r.status == "error")
    n_reg_alert = sum(1 for r in regs if r.get("verdict") == "regressed")
    cards = [
        _stat("projects", len(research.list_projects(lab))),
        _stat("skills", len(lab.skills())),
        _stat("experiments", sum(1 for d in lab.experiments_dir.iterdir()
                                 if (d / "experiment.yaml").is_file())
              if lab.experiments_dir.is_dir() else 0),
        _stat("runs", len(runs)),
        _stat("failed runs", n_fail, "bad" if n_fail else ""),
        _stat("regression alerts", n_reg_alert,
              "bad" if n_reg_alert else "ok"),
    ]
    out = [f'<div class="grid cards">{"".join(cards)}</div>']
    out.append(_mock_note(runs))

    # regression alerts
    alerted = [r for r in regs if r.get("verdict") == "regressed"]
    if alerted:
        rows = []
        for r in alerted:
            rows.append([
                f'<a href="regressions.html#{_esc(r["id"])}">'
                f'{_esc(r["id"])}</a>',
                _esc(r.get("skill", "?")),
                f'{_esc(r.get("baseline"))} → {_esc(r.get("candidate"))}',
                _badge("regressed", "bad"),
                _esc(r.get("created", ""))[:16]])
        out.append("<h2>Regression alerts</h2>" + _table(
            ["regression", "skill", "variants", "verdict", "created"], rows))

    # recent runs — the overview shows the latest few; the full history
    # lives on the Experiments page
    recent = sorted(runs, key=lambda x: x[0].finished or "", reverse=True)[:8]
    if recent:
        rows = []
        for rec, ev in recent:
            rows.append([
                f'<a href="run-{_esc(rec.run_id)}.html">'
                f'{_esc(rec.run_id)}</a>',
                _esc(rec.arm), _esc(rec.task), _sbadge(rec.status),
                _sbadge(ev.status if ev else None),
                f'<span class="num-cell">{_fmt(ev.rubric_score if ev else None)}</span>',
                _esc((rec.finished or "")[:19])])
        out.append("<h2>Recent runs</h2>" + _table(
            ["run", "arm", "task", "run", "eval", "score", "finished"],
            rows))
        if len(runs) > len(recent):
            out.append(f'<p class="muted"><a href="experiments.html">'
                       f'All {len(runs)} runs →</a></p>')
    elif not runs:
        out.append(_empty("No runs yet — run an experiment or a "
                          "regression to populate the dashboard."))
    return "".join(out)


# ------------------------------------------------------------- page: skills


def _skills(lab: Lab, runs) -> str:
    metas = lab.skills()
    if not metas:
        return _empty("No skills registered yet — `lab skill new <id>` "
                      "or `lab skill add <path>`.")
    last_bench: dict[str, str] = {}
    for rec, _ in runs:
        if rec.skill_ref:
            sid, _ = parse_skill_ref(rec.skill_ref)
            if (rec.finished or "") > last_bench.get(sid, ""):
                last_bench[sid] = rec.finished
    rows = []
    for m in metas:
        findings = analyze_skill(lab, m.id)
        n_err = sum(1 for fs in findings.values()
                    for f in fs if f.severity == "error")
        n_warn = sum(1 for fs in findings.values()
                     for f in fs if f.severity == "warn")
        desc = ""
        if m.variants:
            desc = skill_description(
                lab.skills_dir / m.id / m.variants[0].path)[:90]
        sev = (f'{_badge(f"{n_err} errors", "bad")}' if n_err else "") + \
              (f' {_badge(f"{n_warn} warnings", "warn")}' if n_warn else "")
        if not sev:
            sev = _badge("clean", "ok")
        rows.append([
            f'<a href="skill-{_esc(m.id)}.html"><b>{_esc(m.id)}</b></a>',
            _esc(m.kind), _sbadge(m.status),
            ", ".join(f'<span class="badge b-muted">{_esc(v.id)}</span>'
                      for v in m.variants),
            sev, _esc(last_bench.get(m.id, "—")[:16] or "—"),
            _esc(desc)])
    return (_filter("skills-t", "filter skills…") + _table(
        ["skill", "kind", "status", "variants", "findings",
         "last benchmark", "description"], rows, table_id="skills-t"))


# --------------------------------------------------------- page: benchmarks


def _variant_key(rec: RunRecord) -> tuple[str, str] | None:
    if not rec.skill_ref:
        return None
    sid, vid = parse_skill_ref(rec.skill_ref)
    return sid, (vid or "default")


def _benchmarks(lab: Lab, runs) -> str:
    out = [_mock_note(runs)]
    if not runs:
        return _empty("No benchmark data yet — runs appear here after "
                      "experiments complete.")

    # --- variant comparison -------------------------------------------
    by_var: dict[tuple[str, str], list] = {}
    for rec, ev in runs:
        k = _variant_key(rec)
        if k:
            by_var.setdefault(k, []).append((rec, ev))
    if by_var:
        rows, bars = [], []
        maxscore = max((s["score"] or 0)
                       for s in [_stats(v, k[0]) for k, v in by_var.items()]
                       ) or 1.0
        for (sid, vid), rs in sorted(by_var.items()):
            s = _stats(rs, sid)
            label = f"{sid}@{vid}"
            score = s["score"]
            bars.append(_bar(label, score or 0, maxscore,
                             "ok" if (score or 0) == maxscore else ""))
            rows.append([f"<b>{_esc(label)}</b>", str(s["n"]),
                         str(s["errors"]),
                         f'<span class="num-cell">{_fmt(s["success"], 1)}</span>',
                         f'<span class="num-cell">{_fmt(s["score"])}</span>',
                         f'<span class="num-cell">{_fmt(s["activated"], 1)}</span>',
                         f'<span class="num-cell">{_fmt(s["tokens"])}</span>',
                         f'<span class="num-cell">{_fmt(s["latency"])}s</span>',
                         f'<span class="num-cell">{_fmt(s["turns"])}</span>',
                         f'<span class="num-cell">{_fmt(s["variance"])}</span>'])
        out.append("<h2>Variant comparison</h2>"
                   '<div class="section"><h3>rubric score by variant</h3>'
                   + "".join(bars) + "</div>"
                   + _table(["variant", "runs", "err", "success", "score",
                             "activated", "tokens", "latency", "turns",
                             "variance"], rows))

    # --- model comparison ---------------------------------------------
    by_model: dict[str, list] = {}
    for rec, ev in runs:
        by_model.setdefault(str(rec.model.get("name", "?")),
                            []).append((rec, ev))
    if len(by_model) > 1:
        rows = []
        for name, rs in sorted(by_model.items()):
            s = _stats(rs)
            rows.append([f"<b>{_esc(name)}</b>", str(s["n"]),
                         str(s["errors"]),
                         f'<span class="num-cell">{_fmt(s["success"], 1)}</span>',
                         f'<span class="num-cell">{_fmt(s["score"])}</span>',
                         f'<span class="num-cell">{_fmt(s["tokens"])}</span>',
                         f'<span class="num-cell">{_fmt(s["latency"])}s</span>',
                         f'<span class="num-cell">{_fmt(s["variance"])}</span>'])
        out.append("<h2>Model comparison</h2>" + _table(
            ["model", "runs", "err", "success", "score", "tokens",
             "latency", "variance"], rows))

    # --- task-level results --------------------------------------------
    by_task: dict[str, list] = {}
    for rec, ev in runs:
        by_task.setdefault(rec.task, []).append((rec, ev))
    rows = []
    for tid, rs in sorted(by_task.items()):
        s = _stats(rs)
        rows.append([f"<b>{_esc(tid)}</b>", str(s["n"]),
                     f'<span class="num-cell">{_fmt(s["success"], 1)}</span>',
                     f'<span class="num-cell">{_fmt(s["score"])}</span>',
                     f'<span class="num-cell">{_fmt(s["variance"])}</span>',
                     f'<span class="num-cell">{_fmt(s["tokens"])}</span>',
                     f'<span class="num-cell">{_fmt(s["latency"])}s</span>'])
    out.append("<h2>Task-level results</h2>"
               + _filter("tasks-t", "filter tasks…") + _table(
                   ["task", "runs", "success", "score", "variance",
                    "tokens", "latency"], rows, table_id="tasks-t"))

    # --- arm × task pivot (per experiment) ------------------------------
    exp_ids = sorted({r.experiment for r, _ in runs})
    for exp_id in exp_ids:
        exp_runs = [(r, e) for r, e in runs if r.experiment == exp_id]
        arms = sorted({r.arm for r, _ in exp_runs})
        tids = sorted({r.task for r, _ in exp_runs})
        if not arms or not tids:
            continue
        rows = []
        for arm in arms:
            row = [f"<b>{_esc(arm)}</b>"]
            for tid in tids:
                cell_runs = [(r, e) for r, e in exp_runs
                             if r.arm == arm and r.task == tid]
                s = _stats(cell_runs)
                if s["n"] == 0:
                    row.append('<span class="muted">—</span>')
                else:
                    sc = _fmt(s["score"])
                    cls = "b-ok" if (s["score"] or 0) >= 0.6 else \
                        ("b-warn" if (s["score"] or 0) >= 0.4 else "b-bad")
                    row.append(f'<span class="badge {cls}">{sc}</span>'
                               f'<div class="muted" style="font-size:.72rem">'
                               f'n={s["n"]}</div>')
            rows.append(row)
        out.append(f'<h2>{_esc(exp_id)} — arm × task score</h2>' + _table(
            ["arm"] + tids, rows, sortable=False))
    return "".join(out)


# -------------------------------------------------------- page: regressions


def _regressions(lab: Lab) -> str:
    rdir = lab.d("regressions")
    metas = []
    if rdir.is_dir():
        for d in sorted(rdir.iterdir()):
            f = d / "regression.yaml"
            if f.is_file():
                metas.append(load_yaml(f))
    if not metas:
        return _empty("No regression runs yet — "
                      "`lab regression run <skill> --baseline V "
                      "--candidate V`.")
    out = []
    cat_rows: dict[str, list] = {k: [] for k in
                                 ("critical", "quality", "activation",
                                  "false-activation", "efficiency",
                                  "stability")}
    for meta in metas:
        rid = meta["id"]
        rep_file = rdir / rid / "report.yaml"
        rep = load_yaml(rep_file) if rep_file.is_file() else {}
        for t in rep.get("tasks", []):
            for c in t.get("categories", []):
                if c in cat_rows:
                    cat_rows[c].append((rid, t, meta))
        verdict = meta.get("verdict") or "—"
        out.append(
            f'<div class="section" id="{_esc(rid)}"><h2>'
            f'{_esc(meta.get("skill", "?"))}: '
            f'{_esc(meta.get("baseline"))} → {_esc(meta.get("candidate"))} '
            f'{_sbadge(verdict)}</h2>'
            f'<p class="muted">regression <code>{_esc(rid)}</code> · '
            f'model {_esc(meta.get("model","?"))} · '
            f'{_esc(meta.get("injection_mode","?"))} · '
            f'{len(meta.get("tasks", []))} task(s) · '
            f'{_esc(meta.get("created",""))[:16]}</p>')
        if str(meta.get("model", "")).startswith("mock"):
            out.append('<div class="note">mock model — simulated data</div>')
        tasks = rep.get("tasks", [])
        if tasks:
            rows = []
            for t in tasks:
                cats = " ".join(_badge(c, "bad")
                                for c in t.get("categories", []))
                if not cats:
                    cats = _badge("ok", "ok") if not t.get("notes") \
                        else _badge("n/a", "muted")
                mb, mc = t["baseline"], t["candidate"]
                rows.append([
                    f"<b>{_esc(t['task'])}</b>", _esc(t.get("kind", "?")),
                    cats,
                    f'<span class="num-cell">{_fmt(mb.get("success"),1)}</span>',
                    f'<span class="num-cell">{_fmt(mc.get("success"),1)}</span>',
                    f'<span class="num-cell">{_fmt(mb.get("score"))}</span>',
                    f'<span class="num-cell">{_fmt(mc.get("score"))}</span>',
                    "; ".join(_esc(n) for n in t.get("notes", []))])
            out.append(_table(
                ["task", "kind", "verdict", "base succ", "cand succ",
                 "base score", "cand score", "notes"], rows,
                sortable=False))
        out.append("</div>")

    # category summary up top
    cat_html = []
    label = {"critical": "newly failing tasks",
             "quality": "quality degradation",
             "activation": "activation regressions",
             "false-activation": "false activations",
             "efficiency": "efficiency regressions",
             "stability": "stability regressions"}
    for c, items in cat_rows.items():
        if items:
            links = " ".join(
                f'<a href="#{_esc(rid)}"><span class="badge b-bad">'
                f'{_esc(t["task"])}</span></a>' for rid, t, _ in items)
            cat_html.append(
                f'<div class="section"><h3>{_esc(label[c])} '
                f'({len(items)})</h3>{links}</div>')
    return ("".join(cat_html) + "<h2>All regressions</h2>" + "".join(out))


# -------------------------------------------------------- page: experiments


def _experiments(lab: Lab) -> str:
    if not lab.experiments_dir.is_dir():
        return _empty("No experiments yet — `lab experiment new <id>`.")
    exps = []
    for d in sorted(lab.experiments_dir.iterdir()):
        if (d / "experiment.yaml").is_file():
            exps.append((d, lab.experiment(d.name)))
    if not exps:
        return _empty("No experiments yet — `lab experiment new <id>`.")

    rows = []
    for d, exp in exps:
        n = len(load_runs(lab, exp.id))
        rows.append([
            f'<a href="#{_esc(exp.id)}"><b>{_esc(exp.id)}</b></a>',
            _sbadge(exp.status), str(len(exp.arms)), str(n),
            str(len(exp.tasks)), _esc(exp.fixed.model),
            _esc(exp.fixed.injection_mode),
            _esc(exp.title or exp.hypothesis[:60])])
    out = [_filter("exp-t", "filter experiments…") + _table(
        ["experiment", "status", "arms", "runs", "tasks", "model",
         "injection", "title"], rows, table_id="exp-t")]

    for d, exp in exps:
        runs = load_runs(lab, exp.id)
        sec = [f'<div class="section" id="{_esc(exp.id)}">'
               f"<h2>{_esc(exp.id)} {_sbadge(exp.status)}</h2>"]
        if exp.hypothesis:
            sec.append(f"<p><b>hypothesis:</b> {_esc(exp.hypothesis)}</p>")
        arm_list = ", ".join(
            f"{_esc(a.name)}={_esc(a.skill or 'none')}" for a in exp.arms)
        sec.append(
            f'<p class="muted">var: {_esc(exp.independent_var)} · '
            f'model {_esc(exp.fixed.model)} · T={exp.fixed.temperature} · '
            f'{_esc(exp.fixed.injection_mode)} · '
            f'{exp.rollouts_per_arm} rollouts · arms: {arm_list}</p>')

        # per-arm metrics
        arm_rows = []
        for a in exp.arms:
            rs = [(r, e) for r, e in runs if r.arm == a.name]
            if not rs:
                continue
            sid = parse_skill_ref(a.skill)[0] if a.skill else None
            s = _stats(rs, sid)
            arm_rows.append([
                f"<b>{_esc(a.name)}</b>", _esc(a.skill or "—"),
                str(s["n"]), str(s["errors"]),
                f'<span class="num-cell">{_fmt(s["success"],1)}</span>',
                f'<span class="num-cell">{_fmt(s["score"])}</span>',
                f'<span class="num-cell">{_fmt(s["activated"],1) if sid else "—"}</span>',
                f'<span class="num-cell">{_fmt(s["tokens"])}</span>',
                f'<span class="num-cell">{_fmt(s["latency"])}s</span>',
                f'<span class="num-cell">{_fmt(s["variance"])}</span>'])
        if arm_rows:
            sec.append("<h3>arm comparison</h3>" + _table(
                ["arm", "skill", "runs", "err", "success", "score",
                 "activated", "tokens", "latency", "variance"], arm_rows,
                sortable=False))

        # run history
        run_rows = []
        for rec, ev in runs:
            run_rows.append([
                f'<a href="run-{_esc(rec.run_id)}.html">'
                f'{_esc(rec.run_id)}</a>',
                _esc(rec.arm), _esc(rec.task), _sbadge(rec.status),
                _sbadge(ev.status if ev else None),
                f'<span class="num-cell">{_fmt(ev.rubric_score if ev else None)}</span>',
                f'<span class="num-cell">{_fmt(_duration(rec))}s</span>',
                f'<span class="num-cell">{rec.usage.input_tokens + rec.usage.output_tokens}</span>'])
        if run_rows:
            sec.append("<h3>run history</h3>"
                       + _filter(f"runs-{exp.id}", "filter runs…")
                       + _table(["run", "arm", "task", "run", "eval",
                                 "score", "latency", "tokens"], run_rows,
                                table_id=f"runs-{exp.id}"))
        else:
            sec.append(_empty("no runs recorded for this experiment"))
        analysis = d / "analysis.md"
        if analysis.is_file():
            sec.append(f"<details><summary>analysis.md</summary>"
                       f'<pre class="raw">{_esc(analysis.read_text())}'
                       f"</pre></details>")
        sec.append("</div>")
        out.append("".join(sec))
    return "".join(out)


# --------------------------------------------------------- run detail pages


def _transcript_html(tpath: Path) -> str:
    if not tpath.is_file():
        return _empty("no transcript recorded")
    out = []
    for i, line in enumerate(tpath.read_text().splitlines()):
        try:
            m = json.loads(line)
        except json.JSONDecodeError:
            continue
        role = m.get("role", "?")
        head = f'<span class="role-badge">#{i} {_esc(role)}' + \
            (f' [{_esc(m["name"])}]' if m.get("name") else "") + "</span>"
        usage = ""
        if m.get("usage"):
            u = m["usage"]
            usage = (f'<span class="muted" style="float:right;font-size:.72rem">'
                     f'in={u.get("input",0)} out={u.get("output",0)}</span>')
        if role == "assistant" and m.get("tool_calls"):
            for tc in m["tool_calls"]:
                out.append(
                    f'<div class="msg role-assistant" data-frow>{head}'
                    f'{usage} <b>→ {_esc(tc["function"]["name"])}</b><pre>'
                    f'{_esc(tc["function"]["arguments"])}</pre></div>')
        else:
            out.append(
                f'<div class="msg role-{_esc(role)}" data-frow>{head}'
                f'{usage}<pre>{_esc(m.get("content") or "")}</pre></div>')
    return "".join(out)


def _run_page(lab: Lab, rec: RunRecord, ev: EvalResult | None,
              run_dir: Path) -> str:
    body = [
        f'<p><b>experiment:</b> <a href="experiments.html'
        f'#{_esc(rec.experiment)}">{_esc(rec.experiment)}</a> · '
        f'<b>arm:</b> {_esc(rec.arm)} · <b>task:</b> {_esc(rec.task)} · '
        f'<b>model:</b> {_esc(rec.model.get("name"))} · '
        f'<b>mode:</b> {_esc(rec.injection_mode)} · '
        f'<b>skill:</b> {_esc(rec.skill_ref or "none")}</p>',
        f'<div class="grid cards">'
        + _stat("status", _sbadge(rec.status))
        + _stat("eval", _sbadge(ev.status if ev else None))
        + _stat("score", _fmt(ev.rubric_score if ev else None))
        + _stat("turns", rec.usage.turns)
        + _stat("tokens",
                rec.usage.input_tokens + rec.usage.output_tokens)
        + _stat("latency", f"{_fmt(_duration(rec))}s")
        + "</div>"]
    if rec.error:
        body.append(f'<div class="note err"><b>run error:</b> '
                    f'{_esc(rec.error)}</div>')
    if _is_mock(rec):
        body.append('<div class="note">mock model — simulated run</div>')

    # evaluation details
    if ev is not None:
        rows = []
        for c in ev.checks:
            rows.append([
                f"<b>{_esc(c.id)}</b>", _esc(c.method), _sbadge(c.status),
                f'<span class="num-cell">{_fmt(c.score)}</span>',
                _esc(c.judge_model or "—"),
                _esc(c.detail[:120])])
        body.append("<h2>Evaluation</h2>" + _table(
            ["criterion", "method", "status", "score", "judge model",
             "detail"], rows, sortable=False))
        if ev.evaluated_at:
            body.append(f'<p class="muted">evaluated at '
                        f'{_esc(ev.evaluated_at)}</p>')
    else:
        body.append('<div class="note err">no eval.yaml — evaluation '
                    "missing or pending</div>")

    # failure analysis report, if one was written for this run
    frep = lab.d("failures") / f"{rec.run_id}.yaml"
    if frep.is_file():
        r = load_yaml(frep)
        vcls = {"failed": "bad", "warning": "warn",
                "inconclusive": "muted"}.get(r["verdict"], "ok")
        rows = [[_esc(c["category"]), _esc(c["hypothesis"][:110]),
                 f'<span class="muted">{_esc(c["evidence"][:80])}</span>']
                for c in r["causes"]]
        body.append(f"<h2>Failure analysis "
                    f"{_badge(r['verdict'], vcls)}</h2>"
                    + (_table(["category", "hypothesis", "evidence"],
                              rows, sortable=False)
                       if rows else
                       '<p class="muted">no failures detected</p>'))

    # skill events
    if rec.skill_events:
        rows = [[str(e.t), _esc(e.event), _esc(e.skill or "—"),
                 _esc(e.path or "—")] for e in rec.skill_events]
        body.append("<h2>Skill events</h2>" + _table(
            ["turn", "event", "skill", "path"], rows, sortable=False))

    # artifacts
    ws = run_dir / "workspace"
    if ws.is_dir():
        files = sorted(str(p.relative_to(ws))
                       for p in ws.rglob("*") if p.is_file())
        if files:
            items = "".join(f"<li><code>{_esc(f)}</code></li>"
                            for f in files)
            body.append(f"<h2>Artifacts ({len(files)})</h2><ul>{items}</ul>")
        else:
            body.append(_empty("workspace is empty"))

    body.append("<h2>Transcript</h2>"
                + _filter("tr", "filter transcript…")
                + f'<div id="tr">{_transcript_html(run_dir / "transcript.jsonl")}</div>')
    return "".join(body)


# ------------------------------------------------------------ page: insights


def _insights(lab: Lab) -> str:
    from .insights import list_insights
    items = list_insights(lab)
    if not items:
        return _empty("No insights yet — "
                      '`lab insight new "<statement>" --evidence <exp>`')
    out = [_filter("ins-t", "filter insights…"), '<div id="ins-t">']
    for i in items:
        d = lab.insights_dir / f"{i['id']}.md"
        if not d.is_file():
            d = lab.principles_dir / f"{i['id']}.md"
        fm, body_md = parse_frontmatter(d.read_text()) if d.is_file() \
            else ({}, "")
        ev = i.get("evidence") or []
        if isinstance(ev, str):
            ev = [ev]
        ev_links = " ".join(
            f'<a href="experiments.html#{_esc(e)}">'
            f'<span class="badge b-info">{_esc(e)}</span></a>' for e in ev)
        out.append(
            f'<div class="section" data-frow><h2>{_esc(i["id"])} '
            f'{_sbadge(i["status"])} '
            f'{_badge(i.get("confidence", "?"), "purple")} '
            f'{_badge(i["kind"], "muted")}</h2>'
            f'<p><b>scope:</b> {_esc(fm.get("scope") or "—")}</p>'
            f'<p><b>evidence:</b> {ev_links or "—"}</p>'
            f'<pre class="raw">{_esc(body_md.strip() or "(no body)")}</pre>'
            "</div>")
    out.append("</div>")
    return "".join(out)


# -------------------------------------------------------------------- main --


# --------------------------------------------------------- page: research


_PROJ_BADGE = {
    "draft": "muted", "archived": "muted", "completed": "ok",
    "validating": "warn", "experimenting": "warn",
}


def _proj_status(m) -> str:
    return _badge(m.status, _PROJ_BADGE.get(m.status, "info"))


def _research(lab: Lab) -> str:
    projects = research.list_projects(lab)
    if not projects:
        return _empty("No research projects yet — create one with "
                      "`lab project new <id>`.")
    rows = []
    for m in projects:
        s = research.project_summary(lab, m.id)
        rows.append([
            f'<a href="project-{_esc(m.id)}.html">{_esc(m.id)}</a>',
            _esc(m.title),
            _proj_status(m),
            f'<span class="num-cell">{len(s["questions"])}</span>',
            f'<span class="num-cell">{len(s["findings"])}</span>',
            f'<span class="num-cell">{len(s["sources"])}</span>',
            f'<span class="num-cell">{len(s["decisions"])}</span>',
            _esc(m.updated or m.created)])
    return _filter("prj-t", "filter projects…") + _table(
        ["project", "title", "status", "questions", "findings",
         "sources", "decisions", "updated"], rows, table_id="prj-t")


_FINDING_STATUS_BADGE = {"candidate": "warn", "supported": "ok",
                         "refuted": "bad", "inconclusive": "muted"}
_FINDING_KIND_BADGE = {"verified-source": "ok", "observation": "info",
                      "ai-hypothesis": "purple", "unverified": "muted"}


def _project_page(lab: Lab, m) -> str:
    s = research.project_summary(lab, m.id)
    d = research.project_dir(lab, m.id)
    nf, nq = len(s["findings"]), len(s["questions"])
    out = [f"<p>{_proj_status(m)} {_badge(str(nf) + ' findings', 'muted')}"
           f" {_badge(str(nq) + ' questions', 'muted')}</p>"]
    if m.objective:
        out.append(f'<div class="note info"><b>Objective</b> — '
                   f"{_esc(m.objective)}</div>")
    if m.problem:
        out.append(f'<div class="note"><b>Problem</b> — '
                   f"{_esc(m.problem)}</div>")
    charter = d / "charter.md"
    if charter.is_file():
        fm, body = parse_frontmatter(charter.read_text())
        out.append(f"<details><summary>charter.md</summary>"
                   f'<pre class="raw">{_esc(body.strip())}</pre></details>')

    qs = s["questions"]
    out.append("<h2>Research questions</h2>" + (
        _table(["id", "question", "status", "hypothesis", "findings",
                "experiments"],
               [[_esc(q.id), _esc(q.question), _sbadge(q.status),
                 _esc(q.hypothesis), _esc(", ".join(q.findings)),
                 _esc(", ".join(q.experiments))] for q in qs])
        if qs else _empty("none — `lab question add`")))

    fs = s["findings"]
    out.append("<h2>Findings</h2>" + (
        _table(["id", "statement", "kind", "confidence", "status",
                "question", "evidence"],
               [[_esc(f.id), _esc(f.statement),
                 _badge(f.kind, _FINDING_KIND_BADGE.get(f.kind, "muted")),
                 _esc(f.confidence),
                 _badge(f.status,
                        _FINDING_STATUS_BADGE.get(f.status, "muted")),
                 _esc(f.question),
                 _esc(", ".join(f.sources + f.evidence))]
                for f in fs])
        if fs else _empty("none — `lab finding add`")))

    ss = s["sources"]
    out.append("<h2>Sources</h2>" + (
        _table(["id", "type", "title", "author", "ref", "accessed"],
               [[_esc(x.id), _esc(x.type), _esc(x.title), _esc(x.author),
                 _esc(x.url or x.path), _esc(x.accessed)] for x in ss])
        if ss else _empty("none — `lab source add`")))

    ds = s["decisions"]
    out.append("<h2>Decisions</h2>" + (
        _table(["id", "decision", "status", "rationale", "created"],
               [[_esc(x.id), _esc(x.decision), _sbadge(x.status),
                 _esc(x.rationale), _esc(x.created)] for x in ds])
        if ds else _empty("none — `lab decision add`")))

    ns = s["notes"]
    out.append("<h2>Notes</h2>" + (
        _table(["note", "created"],
               [[_esc(n["id"]), _esc(n["created"])] for n in ns])
        if ns else _empty("none — `lab note add`")))

    bps = blueprint.list_blueprints(lab, m.id)
    out.append("<h2>Blueprints</h2>" + (
        _table(["blueprint", "title", "status", "rev", "issues",
                "findings", "updated"],
               [[f'<a href="blueprint-{_esc(m.id)}-{_esc(b.id)}.html">'
                 f'{_esc(b.id)}</a>',
                 _esc(b.title),
                 _badge(b.status, _BP_BADGE.get(b.status, "info")),
                 f"r{b.rev}",
                 _bp_issue_cell(lab, m.id, b.id),
                 _esc(", ".join(b.related_findings)),
                 _esc(b.updated)] for b in bps])
        if bps else _empty("none — `lab blueprint new`")))
    return "".join(out)


_BP_BADGE = {"draft": "muted", "designing": "muted", "archived": "muted",
             "ready_for_generation": "info", "generated": "info",
             "testing": "warn", "improving": "warn",
             "validated": "ok", "released": "ok"}


def _bp_issue_cell(lab: Lab, pid: str, bid: str) -> str:
    issues = blueprint.validate(lab, pid, bid)
    errs = sum(1 for i in issues if i["severity"] == "error")
    warns = len(issues) - errs
    if not issues:
        return _badge("clean", "ok")
    parts = []
    if errs:
        parts.append(_badge(f"{errs} errors", "bad"))
    if warns:
        parts.append(_badge(f"{warns} warnings", "warn"))
    return " ".join(parts)


def _blueprint_page(lab: Lab, pid: str, bid: str) -> str:
    b = blueprint.get_blueprint(lab, pid, bid)
    out = [f"<p>{_badge(b.status, _BP_BADGE.get(b.status, 'info'))} "
           f"{_badge(f'rev r{b.rev}', 'muted')} "
           f'{_badge(f"project {pid}", "muted")}</p>']
    issues = blueprint.validate(lab, pid, bid)
    if issues:
        rows = [[_badge(i["severity"],
                       "bad" if i["severity"] == "error" else "warn"),
                 _esc(i["check"]), _esc(i["field"]), _esc(i["message"])]
                for i in issues]
        out.append("<h2>Validation</h2>" + _table(
            ["severity", "check", "field", "message"], rows))
    rows = []
    for key, kind, req, label in blueprint.FIELDS:
        v = b.fields.get(key)
        if isinstance(v, list):
            disp = "<br>".join(_esc(x) for x in v) or "—"
        else:
            disp = _esc(v) if v else "—"
        rows.append([f"<code>{_esc(key)}{'*' if req else ''}</code>",
                     _esc(label), disp])
    out.append("<h2>Spec fields <span class='muted'>"
               "(* required for generation)</span></h2>"
               + _table(["field", "meaning", "value"], rows,
                        sortable=False))
    if b.related_findings:
        out.append(f"<p class='muted'>related findings: "
                   f"{_esc(', '.join(b.related_findings))}</p>")
    revs = blueprint.revisions(lab, pid, bid)
    if len(revs) > 1:
        out.append("<h2>Revisions</h2>" + _table(
            ["rev", "status", "updated"],
            [[f"r{x.rev}", _esc(x.status), _esc(x.updated)]
             for x in revs]))
    return "".join(out)


def generate(lab: Lab) -> Path:
    out = lab.d("ui")
    out.mkdir(exist_ok=True)
    runs = _all_runs(lab)

    from .regression import list_regressions
    regs = list_regressions(lab)

    (out / "research.html").write_text(
        _page(lab, "Research Projects", _research(lab), "research"))
    for m in research.list_projects(lab):
        (out / f"project-{m.id}.html").write_text(
            _page(lab, f"project: {m.id}", _project_page(lab, m),
                  "research"))
        for b in blueprint.list_blueprints(lab, m.id):
            (out / f"blueprint-{m.id}-{b.id}.html").write_text(
                _page(lab, f"blueprint: {b.id}",
                      _blueprint_page(lab, m.id, b.id), "research"))

    (out / "index.html").write_text(
        _page(lab, f"SkillLab — {lab.root.name}",
              _overview(lab, runs, regs), "index"))
    (out / "skills.html").write_text(
        _page(lab, "Skill Registry", _skills(lab, runs), "skills"))
    (out / "benchmarks.html").write_text(
        _page(lab, "Benchmark Center", _benchmarks(lab, runs),
              "benchmarks"))
    (out / "regressions.html").write_text(
        _page(lab, "Regression Center", _regressions(lab), "regressions"))
    (out / "experiments.html").write_text(
        _page(lab, "Experiment Explorer", _experiments(lab),
              "experiments"))
    (out / "insights.html").write_text(
        _page(lab, "Knowledge Base", _insights(lab), "insights"))

    # per-skill detail pages
    for m in lab.skills():
        sruns = [(r, e) for r, e in runs
                 if r.skill_ref and parse_skill_ref(r.skill_ref)[0] == m.id]
        findings = analyze_skill(lab, m.id)
        frows = []
        for vid, fs in findings.items():
            for f in fs:
                sev = {"error": "bad", "warn": "warn"}.get(
                    f.severity, "muted")
                frows.append([_esc(vid), _badge(f.severity, sev),
                              _esc(f.check), _esc(f.message)])
        body = (f"<p>{_badge(m.kind, 'muted')} {_sbadge(m.status)} "
                f"{_badge(f'{len(m.variants)} variants', 'info')}</p>")
        # per-variant comparison bars
        by_var = {}
        for rec, ev in sruns:
            k = _variant_key(rec)
            if k:
                by_var.setdefault(k[1], []).append((rec, ev))
        if len(by_var) > 1:
            stats = {v: _stats(rs, m.id) for v, rs in by_var.items()}
            mx = max((s["score"] or 0) for s in stats.values()) or 1.0
            bars = "".join(
                _bar(v, s["score"] or 0, mx,
                     "ok" if (s["score"] or 0) == mx else "")
                for v, s in sorted(stats.items()))
            body += ('<div class="section"><h3>variant comparison — '
                     'rubric score</h3>' + bars + "</div>")
        body += "<h2>Findings</h2>" + (
            _table(["variant", "severity", "check", "message"], frows)
            if frows else "<p>no findings</p>")
        # releases for this skill
        from .release import list_releases
        rels = list_releases(lab, m.id)
        if rels:
            rcls = {"released": "ok", "validated": "info",
                    "deprecated": "muted"}
            body += "<h2>Releases</h2>" + _table(
                ["version", "variant", "status", "released", "changelog"],
                [[_esc(r.version), _esc(r.variant or "—"),
                  _badge(r.status, rcls.get(r.status, "warn")),
                  _esc((r.released_at or "")[:16]),
                  _esc(r.changelog[:80])] for r in rels])
        srows = [[f'<a href="run-{_esc(r.run_id)}.html">{_esc(r.run_id)}</a>',
                  _esc(r.skill_ref or ""), _esc(r.experiment), _esc(r.task),
                  _sbadge(r.status), _sbadge(e.status if e else None),
                  f'<span class="num-cell">{_fmt(e.rubric_score if e else None)}</span>']
                 for r, e in sruns]
        body += ("<h2>Runs by variant</h2>" + (
            _filter("sr-t", "filter runs…")
            + _table(["run", "variant", "experiment", "task", "run",
                      "eval", "score"], srows, table_id="sr-t")
            if srows else _empty("no runs recorded against this skill")))
        for v in m.variants:
            entry = lab.skills_dir / m.id / v.path / "SKILL.md"
            if entry.is_file():
                body += (f"<details><summary>variant "
                         f"{_esc(v.id)} — SKILL.md</summary>"
                         f'<pre class="raw">{_esc(entry.read_text())}'
                         "</pre></details>")
        (out / f"skill-{m.id}.html").write_text(
            _page(lab, f"skill: {m.id}", body, "skills"))

    # per-run detail pages
    for rec, ev in runs:
        run_dir = lab.runs_dir / rec.run_id
        (out / f"run-{rec.run_id}.html").write_text(
            _page(lab, f"run: {rec.run_id}",
                  _run_page(lab, rec, ev, run_dir), "experiments"))
    return out
