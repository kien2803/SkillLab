# Skill Lab — System Spec

> Môi trường nghiên cứu và chế tạo skill cho agent AI.
> Mục tiêu: biến việc thiết kế skill từ kinh nghiệm cá nhân thành thực hành có thể
> nghiên cứu, đo lường và tích lũy tri thức.

---

## 0. Thuật ngữ & mô hình khái niệm

| Khái niệm | Định nghĩa |
|---|---|
| **Skill** | Một "instruction artifact" — đơn vị chỉ dẫn được tiêm vào context của agent. SKILL.md là một subtype (frontmatter + progressive disclosure resources). Các loại khác: prompt fragment, system prompt block, tool description. |
| **Variant** | Một phiên bản cụ thể của skill. Một skill có nhiều variant để so sánh có kiểm soát. |
| **Task** | Một bài toán/tình huống chuẩn dùng để kích hoạt hoặc kiểm thử skill. Nằm trong Task Bank, tái sử dụng xuyên suốt experiments. |
| **Arm** | Một nhánh của experiment = một cấu hình skill cụ thể (kể cả arm "control" không có skill). |
| **Rollout / Run** | Một lần chạy agent (LLM + harness) trên một task với một arm. Experiment = nhiều rollouts × nhiều arms × nhiều tasks. |
| **Insight** | Tri thức rút ra từ experiment, có link tới evidence, confidence level và điều kiện áp dụng. |
| **Principle** | Insight được tái xác nhận qua nhiều experiment — nguyên lý thiết kế skill. |

Nguyên tắc xuyên suốt: **một experiment chỉ thay đổi MỘT biến độc lập**
(controlled comparison). Hệ thống enforce điều này ở mức schema và lint.

---

## 1. Kiến trúc tổng quan

File-based core — mọi thứ là file text (YAML/Markdown/JSONL), git-friendly,
diff được, không phụ thuộc database. UI đọc core này ở phase sau.

```
skill-lab/
├── lab.yaml                  # config: model, paths, defaults
├── skills/                   # Skill Registry
│   └── <skill-slug>/
│       ├── skill.yaml        # metadata, kind, tags, status
│       └── variants/
│           ├── v1/SKILL.md
│           └── v2/SKILL.md
├── tasks/                    # Task Bank
│   └── <task-slug>/
│       ├── task.yaml         # prompt, fixture ref, relevance, rubric ref
│       └── fixtures/         # repo/file snapshot cho rollout
├── rubrics/                  # tiêu chí chấm điểm tái sử dụng
│   └── <rubric-slug>.yaml
├── experiments/              # định nghĩa + kết quả tổng hợp
│   └── <exp-id>/
│       ├── experiment.yaml
│       └── analysis.md       # kết luận, link tới insight
├── runs/                     # raw rollout output (append-only)
│   └── <run-id>/
│       ├── run.yaml          # provenance: exp, arm, task, model, seed, hash
│       ├── transcript.jsonl  # toàn bộ messages + tool calls
│       ├── artifacts/        # file agent tạo/sửa
│       └── eval.yaml         # kết quả chấm
├── insights/                 # tri thức tích lũy
│   └── <insight-slug>.md
└── principles/               # insight đã promote thành nguyên lý
    └── <principle-slug>.md
```

### Các component logic

| Component | Trách nhiệm |
|---|---|
| **Registry** | Quản lý skill + variants; content-hash mỗi variant để truy vết. |
| **Task Bank** | Kho task chuẩn, phân loại activation-task và performance-task. |
| **Static Analyzer** | Lint skill không cần chạy (xem §6). |
| **Rollout Engine** | Chạy LLM agent có kiểm soát, thu transcript (xem §4). |
| **Evaluator** | Chấm kết quả: deterministic checks + LLM-judge theo rubric (xem §5). |
| **Report/Diff** | So sánh arms, phát hiện khác biệt có ý nghĩa, đề xuất insight. |
| **Insight Store** | Tri thức có evidence-link, confidence, scope (xem §7). |

---

## 2. Data model

### 2.1 Skill

```yaml
# skills/<slug>/skill.yaml
id: git-commit-helper
kind: skill-md            # skill-md | prompt-fragment | system-prompt | tool-desc
created: 2026-11-12
status: draft             # draft | testing | graduated | archived
tags: [git, workflow]
variants:
  - id: v1-baseline
    path: variants/v1/SKILL.md
    note: "bản đầu tiên"
  - id: v2-terse
    path: variants/v2/SKILL.md
    note: "rút gọn description, giữ nguyên body"
```

Mỗi variant được định danh bằng `(skill-id, variant-id, content-hash)`.
Run record luôn ghi content-hash → kết quả không thể "trôi" khi file đổi.

### 2.2 Task

```yaml
# tasks/<slug>/task.yaml
id: refactor-auth-module
kind: performance         # performance | activation-positive | activation-negative
prompt: prompts/main.md   # hoặc inline
fixtures:
  - fixtures/auth-repo/   # snapshot files agent sẽ làm việc trên
skill_relevance:
  expected: [refactoring-assistant]   # activation-positive: skill NÊN kích hoạt
  unexpected: []                      # activation-negative: skill KHÔNG nên kích hoạt
rubric: refactor-quality
deterministic_checks:
  - type: tests-pass
    command: "pytest tests/"
  - type: file-exists
    path: "src/auth/handler.py"
  - type: file-content                 # nội dung file
    path: "OUTPUT.md"
    contains: "migrate"                # hoặc regex: /equals:
  - type: json                         # JSON hợp lệ + keys/field
    path: "result.json"
    keys: [status]
    field: "status.code"
    value: "0"
  - type: script                       # chạy script trong workspace
    path: "scripts/verify.sh"
```

Check types: `file-exists`, `file-content` (contains/regex/equals),
`json` (keys/field/value), `command` (exit status), `script` (test suite
hoặc custom check chạy qua `bash <path>` — cũng qua sandbox policy).

Hai loại task phục vụ hai câu hỏi khác nhau:

- **Activation task**: skill có được chọn đúng lúc không? (đo trigger quality)
- **Performance task**: khi skill đã active, kết quả có tốt hơn baseline không? (đo nội dung)

Một task bank tốt cần cả negative cases — task trông *giống* nên dùng skill
nhưng thực ra không — để đo false-activation.

### 2.3 Experiment

```yaml
# experiments/<exp-id>/experiment.yaml
id: exp-2026-11-12-trigger-wording
title: "Description chứa ví dụ cụ thể có tăng activation accuracy không?"
hypothesis: "Variant có concrete trigger examples đạt activation rate cao hơn ≥20% mà không tăng false-activation"
independent_var: skill_variant        # DUY NHẤT một biến
created: 2026-11-12
status: designed                      # designed | running | analyzed | concluded
fixed:
  model: claude-sonnet-4.5
  temperature: 0
  seed_policy: varied                 # fixed | varied — varied đo stability
  harness: standard-tools-v1
  injection_mode: available           # available | injected (xem §4)
arms:
  - name: control
    skill: null
  - name: treatment-v1
    skill: git-commit-helper@v1-baseline
  - name: treatment-v2
    skill: git-commit-helper@v2-terse
tasks: [commit-msg-simple, commit-msg-ambiguous, unrelated-refactor]
rollouts_per_arm: 5
metrics: [activation_rate, false_activation, rubric_score, token_cost, turns]
conclusion: null                      # điền khi status=concluded
insights_generated: []
```

### 2.4 Run

```yaml
# runs/<run-id>/run.yaml
run_id: run-2026-11-12-a3f9
experiment: exp-2026-11-12-trigger-wording
arm: treatment-v2
task: commit-msg-ambiguous
model: { name: claude-sonnet-4.5, temperature: 0 }
seed: 42
skill_hash: sha256:...
started: ...
finished: ...
usage: { input_tokens: 8123, output_tokens: 2104, turns: 7 }
skill_events:                          # observability cốt lõi
  - { t: 1, event: offered }           # skill xuất hiện trong registry listing
  - { t: 2, event: activated }         # agent đọc SKILL.md
  - { t: 3, event: resource_read, path: "resources/conventions.md" }
```

`transcript.jsonl` ghi toàn bộ message + tool call, không lược bỏ —
đây là dữ liệu gốc cho mọi phân tích sau này.

### 2.5 Rubric

```yaml
# rubrics/refactor-quality.yaml
id: refactor-quality
criteria:
  - id: correctness
    weight: 0.5
    method: deterministic             # deterministic | llm-judge | human
    check: tests-pass
  - id: code-quality
    weight: 0.3
    method: llm-judge
    judge_prompt: prompts/code-quality.md
    scale: 1-5
  - id: minimal-diff
    weight: 0.2
    method: deterministic
    script: scripts/diff_size.sh
```

Ưu tiên deterministic checks khi có thể; LLM-judge cho tiêu chí mềm;
human slot dành cho chấm tay khi cần (judgment call).

**Evaluation lifecycle** (eval.yaml): mỗi check và eval tổng có `status` ∈
`pending | passed | failed | error`. `error` = hạ tầng chấm hỏng (judge
outage, check config sai, check path escape workspace) — không bao giờ
trộn với task failure. Eval có criterion pending/error thì eval tổng
không thể `passed`. Provenance: `evaluated_at` timestamp + `judge_model`
trên từng judge check; `lab eval <run> --score crit=val
--comment crit=text` điền human scores (comment criterion-level).

### 2.6 Insight

```markdown
---
id: trigger-specificity
confidence: high                       # high | medium | low
evidence: [exp-2026-11-12-trigger-wording, exp-2026-10-30-desc-length]
scope: [skill-md, trigger, description]
status: candidate                      # candidate | confirmed | refuted | promoted
---
## Phát biểu
Description chứa 2-3 ví dụ tình huống cụ thể tăng activation accuracy
~25% so với description trừu tượng, không tăng false-activation.

## Điều kiện áp dụng
- Model: sonnet-class trở lên (haiku chưa kiểm chứng)
- Task: activation-positive, prompt ngắn

## Phản ví dụ / giới hạn
- exp-xxx: trên task đa bước, ví dụ cụ thể gây over-trigger
```

---

## 3. User flows chính

### Flow A — Nghiên cứu một skill có sẵn

1. `lab skill add ./my-skill/` → đăng ký vào registry, tạo variant v1
2. `lab analyze git-commit-helper` → static report: token cost, trigger
   surface, xung đột với skill khác, anti-patterns
3. Người dùng tạo variant v2 (sửa một khía cạnh)
4. `lab experiment new` → khai báo hypothesis, arms, tasks
5. `lab run exp-xxx` → N rollouts × arms × tasks
6. `lab report exp-xxx` → bảng so sánh, transcript highlights
7. `lab insight add --from exp-xxx` → ghi insight có evidence-link

### Flow B — Chế tạo skill mới có cấu trúc

1. `lab skill new` → scaffold theo template progressive disclosure
   (SKILL.md mỏng + resources/)
2. Linter chạy liên tục trong quá trình viết → phản hồi sớm
3. Build task bank cho skill: ít nhất 2 activation-positive,
   1 activation-negative, 1 performance
4. Baseline experiment: skill vs. no-skill control → skill có giá trị không?
5. Iterate: variant → experiment → insight → variant

### Flow C — Truy vết & tái tạo

1. `lab insight show trigger-specificity` → phát biểu + evidence chain
2. Click/ngược về `exp-xxx` → experiment.yaml + analysis.md
3. `lab runs exp-xxx --arm treatment-v2` → từng transcript
4. `lab rerun exp-xxx` → tái tạo với cùng config, model mới hơn nếu muốn
   so sánh drift theo model version

### Flow D — Tích lũy tri thức

1. Insight đạt confidence cao qua ≥2 experiments độc lập → `lab promote` → principle
2. Principles được inject ngược vào Static Analyzer: skill mới được lint
   theo nguyên lý đã kiểm chứng → **vòng phản hồi tri thức**
3. `lab principles` → "bộ giáo trình" skill design do chính lab tạo ra

---

## 4. Rollout Engine (experiment engine)

### 4.1 Controlled setup

Mọi thứ cố định trừ biến độc lập:

| Thành phần | Cố định bởi |
|---|---|
| Model + temperature + seed policy | `experiment.fixed` |
| System prompt khung của agent | `harness` version (standard-tools-v1) |
| Toolset | harness version |
| Task prompt + fixtures | task bank |
| Skill (arm) | **biến độc lập duy nhất** |

### 4.2 Hai chế độ tiêm skill (injection_mode)

- **`available`**: agent chỉ thấy registry listing (name + description của tất
  cả skill trong registry). Muốn dùng phải chủ động đọc → mô phỏng progressive
  disclosure thật → **đo trigger/activation**.
- **`injected`**: toàn bộ nội dung skill đặt sẵn trong context → **đo chất
  lượng nội dung** khi đã được dùng.

Experiment activation dùng `available`; experiment nội dung dùng `injected`.
Trộn hai chế độ trong một experiment = mất controlled comparison (lint cảnh báo).

### 4.3 Toolset chuẩn (standard-tools-v1)

Tối thiểu để agent thực thi task trong fixtures: `read_file`, `write_file`,
`list_dir`, `run_command` (sandboxed trong fixture dir), `read_skill`.
Mọi tool call ghi vào transcript kèm timestamp → `skill_events` suy ra được
khi nào agent quyết định load skill, đọc resource nào.

### 4.4 Observability requirements

- Transcript đầy đủ, append-only, JSONL
- Skill events trích xuất tự động: offered → activated → resource_read
- Token usage per-turn, không chỉ tổng
- Nhiều rollouts/arm (mặc định ≥5) để đo variance — kết luận từ 1 run
  là anti-pattern mà hệ thống phải ngăn (report layer cảnh báo khi n<3)

---

## 5. Evaluation & Metrics

### Nhóm 1 — Activation (chế độ `available`)

| Metric | Ý nghĩa |
|---|---|
| activation_rate | % rollouts skill được load trên activation-positive tasks |
| false_activation_rate | % rollouts skill được load trên negative tasks |
| time_to_activation | turn index khi skill được load (sớm = trigger rõ) |

### Nhóm 2 — Outcome (cả hai chế độ)

| Metric | Ý nghĩa |
|---|---|
| rubric_score | weighted score theo rubric (deterministic + llm-judge) |
| task_success | pass/fail theo deterministic_checks |
| delta_vs_control | chênh lệch so với arm không-skill — **giá trị thật của skill** |

### Nhóm 3 — Efficiency

| Metric | Ý nghĩa |
|---|---|
| token_cost | input+output tokens; skill nặng phải chứng minh giá trị tương xứng |
| skill_load_cost | tokens skill chiếm khi load (SKILL.md + resources đọc) |
| turns | số vòng agent cần để xong task |

### Nhóm 4 — Stability

| Metric | Ý nghĩa |
|---|---|
| outcome_variance | độ phân tán rubric_score trong cùng arm |
| cross_task_consistency | skill có tổng quát hay chỉ tốt trên 1 task |

### Report layer

`lab report exp-xxx` sinh bảng so sánh arms × metrics, đánh dấu khác biệt
vượt ngưỡng ý nghĩa, cảnh báo khi sample nhỏ hoặc variance cao, và đề xuất
(có thể bằng LLM) insight candidate để người dùng duyệt — **người dùng quyết
định insight, hệ thống chỉ đề xuất** (đúng nguyên tắc "tri thức hơn công cụ").

---

## 6. Static Analyzer (không cần chạy)

Chạy được ngay trên skill file, dùng cho Flow B và pre-experiment check:

| Check | Phát hiện |
|---|---|
| frontmatter-valid | thiếu name/description, sai schema |
| description-quality | description trừu tượng, không có trigger condition, quá dài/quá ngắn |
| token-budget | SKILL.md vượt ngưỡng (~500 dòng), nội dung nặng đáng lẽ nằm trong resources/ |
| progressive-disclosure | toàn bộ chi tiết nhồi vào file chính thay vì tách resource |
| dead-links | reference tới resource không tồn tại |
| trigger-conflict | overlap trigger giữa các skill trong registry (LLM/embedding judge) → activation contention |
| anti-patterns | chỉ dẫn quá prescriptive cho model mạnh, lặp lại kiến thức mặc định của model, thiếu ràng buộc output |
| principle-conformance | vi phạm principles đã được lab kiểm chứng (§7 feedback loop) |

---

## 7. Insight & Knowledge Layer

- Insight **bắt buộc** link evidence (experiment hoặc run cụ thể) — insight
  không evidence chỉ ở trạng thái `candidate`.
- Confidence promotion path: `candidate → confirmed` (≥2 experiments độc lập
  cùng kết luận) → `principle` (đủ tổng quát, có điều kiện áp dụng rõ).
- `refuted` không bị xóa — insight bị bác bỏ cũng là tri thức.
- Principles feed back vào Static Analyzer → lab tự tích lũy năng lực lint.
- Mọi insight có `scope` để tránh over-generalize (phát hiện trên model X
  không tự động áp cho model Y).

---

## 8. Reproducibility

- Mọi artifact text-based → `git` version toàn bộ lab.
- Run ghi content-hash của skill, prompt hash, model name, seed, harness version.
- `lab rerun exp-xxx` tái tạo đúng config; cho phép override một trường
  (vd. model) để đo drift theo thời gian — đây cũng là một loại experiment.
- Experiment ở `concluded` bất biến: sửa skill sau đó tạo experiment mới,
  không ghi đè lịch sử.

---

## 9. Roadmap

**Phase 1 — Core loop (MVP)**
- Cấu trúc thư mục + schemas (skill, task, experiment, run)
- Static analyzer: frontmatter, token-budget, dead-links, description-quality
- Rollout engine tối thiểu: 1 model, standard-tools-v1, cả 2 injection modes
- Deterministic checks + report bảng đơn giản
- Insight store (file-based, chưa có promote flow)

**Phase 2 — Evaluation & knowledge**
- LLM-judge theo rubric, judge_prompt templates
- Confidence promotion → principles, feedback vào analyzer
- Trigger-conflict detection, anti-pattern checks mở rộng
- Report có transcript diff highlights + insight suggestion

**Phase 3 — Scale & share**
- UI đọc core (diff viewer, experiment dashboard, insight graph)
- Multi-model comparison (model là biến độc lập hợp lệ)
- Export/import insight pack — nền cho tri thức cộng đồng
- Task bank chia sẻ được

---

## 10. Quyết định còn mở (cần chốt trước khi build)

Đã chốt khi implement:

1. **Ngôn ngữ implementation**: Python — `skilllab/` package, `lab` CLI.
2. **LLM provider**: abstraction qua litellm (optional extra `[llm]`);
   `model: mock` là backend offline xác định cho dev/test.
3. **Sandbox `run_command`**: subprocess, cwd giới hạn trong run workspace,
   timeout 60s. Container hóa ở Phase 3 nếu cần.
4. **Ngưỡng `graduated`**: implement ở `lab skill evaluate` — activation ≥80%,
   false-activation ≤20%, delta dương trên ≥3 performance tasks, n≥9 runs;
   override qua `graduation:` trong lab.yaml.
5. **Judge model**: `judge_model` riêng trong lab.yaml — mặc định kỳ vọng
   mạnh hơn rollout model.
6. **Registry scope**: `lab skill add <path>` import được skill từ bất kỳ
   đâu (kể cả `~/.agents/skills`).

## Addendum — quyết định phát sinh khi implement

- **Variable-skill isolation**: skill xuất hiện trong *bất kỳ* arm nào là
  biến độc lập → bị ẩn khỏi mọi arm `skill: null` và chỉ arm tương ứng mới
  thấy variant của nó. Nếu không, control arm âm thầm được offer chính skill
  đang thử (bug đã gặp thực tế).
- **run_id + batch**: `lab rerun --batch <name>` (hoặc `--model` → batch tự
  sinh từ tên model) để rerun giữ lịch sử append-only; rerun không batch sẽ
  overwrite run cũ (idempotent).
- **Activation metrics chỉ tính ở `injection_mode: available`** — ở injected
  mode agent không tự quyết định load skill nên activation vô nghĩa.
- **Principle lint rules**: principle frontmatter có thể mang `lint:` rules
  (`field: description|body|entry`, `pattern`, `negate`, `severity`,
  `message`) — đây là cơ chế vòng phản hồi tri thức ở §7. Matching
  case-insensitive.
- **Mock model**: backend `mock`/`mock:*` mô phỏng agent xác định (activate
  theo keyword overlap, viết OUTPUT.md, đọc resources) — đủ để chạy toàn
  pipeline offline và test CI.
- **UI**: `lab ui` sinh static HTML dashboard trong `ui/` — không cần
  server/deps, vẫn giữ file-based core là source of truth. Sáu trang:
  Overview (stats, regression alerts, recent runs), Skills, Benchmarks
  (variant/model/task + arm×task matrix), Regressions (theo category),
  Experiments (config, arm metrics, run history), Knowledge Base
  (insight/principle + evidence). Per-run pages có eval checks, skill
  events, artifacts, transcript lọc được. Tất cả số liệu đọc từ
  run.yaml/eval.yaml/regression records — không fabricate; mock data
  được gán nhãn simulated.
- **Sharing**: `lab export`/`lab import` với pack = thư mục + `pack.yaml`
  manifest (`kind: skilllab-pack`, `version: 1`) — insights, principles,
  tasks. Import validate manifest: chỉ 3 thư mục trên được phép, entry
  traversal bị từ chối, symlink không được copy, task.yaml sai schema bị
  reject; dest resolve phải nằm trong lab. Output báo
  imported/skipped/rejected rõ ràng.
- **Multi-model**: `By model` section trong report tự xuất hiện khi runs
  span >1 model (via `rerun --model` hoặc arm-level `model:`).
- **Sandbox**: `sandbox:` trong lab.yaml quyết định execution policy cho
  `run_command`, deterministic command checks VÀ `cmd:` drivers (shared
  helper `run_in_workspace`, `command_timeout` giây/timeout):
  - `bwrap` — cô lập: unshare-all (không network), system read-only, chỉ
    workspace writable; thiếu bwrap → lỗi rõ ràng.
  - `unsafe` — shell không giới hạn trong workspace (opt-in tường minh;
    `cwd=` KHÔNG phải security boundary).
  - unset/khác — **commands disabled, fail closed**; không silent fallback.
- **Run history append-only**: `run_rollout` từ chối run_id đã tồn tại;
  `--force` không xóa mà move run cũ sang `archive/<run_id>/<ts>/`.
- **Regression testing**: `lab regression run <skill> --baseline V
  --candidate V --tasks SUITE` tạo experiment 2-arm (cùng fixed config →
  equivalence theo construction) rồi so sánh từng task. Record ở
  `regressions/reg-<skill>-<b>-<c>-<NN>/` (regression.yaml + report.md +
  report.yaml). Categories: critical (passed→failed), quality (score
  giảm), activation (mất trigger trên positive task), false-activation
  (trigger trên negative task), efficiency (token/latency tăng),
  stability (variance tăng) — threshold trong `lab.yaml` `regression:`,
  override bằng `--threshold k=v`. `min_runs` đánh dấu insufficient
  data; eval thiếu/pending/error KHÔNG tính là fail; report có banner
  cảnh báo khi model=mock. `lab regression list`, `lab regression report
  <id>` tái tạo report từ run data đã lưu.
- **Diff viewer**: `lab diff <runA> <runB>` — unified diff của transcript
  flow + workspace outputs; `lab transcript` xem một run.
- **Lifecycle**: `experiment conclude --conclusion ... --insight <id>`
  đóng experiment và link insight; `insight show/list/promote`;
  `status` = health check (missing fixtures, runs thiếu eval).
