"""LLM client abstraction.

Two backends:
- 'mock': deterministic offline simulation — activates a listed skill when its
  description shares keywords with the task prompt, writes OUTPUT.md, stops.
  Lets the whole lab pipeline run with no API key.
- litellm: any provider string litellm understands ('gpt-4o',
  'anthropic/claude-sonnet-4-5', 'gemini/…', …).
"""

from __future__ import annotations

import json
import re
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class LLMReply:
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0


class LLMClient:
    def __init__(self, model: str, temperature: float = 0.0,
                 seed: Optional[int] = None, timeout: float = 120,
                 max_retries: int = 3, cwd: Optional[str] = None):
        self.model = model
        self.temperature = temperature
        self.seed = seed
        self.timeout = timeout
        self.max_retries = max_retries
        self.cwd = cwd
        self.is_mock = model == "mock" or model.startswith("mock:")
        self.is_cmd = model.startswith("cmd:")

    def complete(self, messages: list[dict],
                 tools: Optional[list[dict]] = None) -> LLMReply:
        if self.is_mock:
            return _mock_complete(messages, tools or [])
        if self.is_cmd:
            return _cmd_complete(self.model[4:], messages, tools or [],
                                 self.timeout, self.cwd)
        return _litellm_complete(self.model, self.temperature, self.seed,
                                 messages, tools, self.timeout,
                                 self.max_retries)


# ------------------------------------------------------- cmd: driver backend --
#
# `model: cmd:<shell command>` runs an external agent/driver once per turn.
# stdin gets one JSON object: {"messages": [...], "tools": [...]}; stdout must
# be a single JSON object:
#   {"content": "...", "tool_calls": [{"name": ..., "arguments": {...}}],
#    "input_tokens": 0, "output_tokens": 0}
# The driver runs with cwd = run workspace, so it can read/write task files
# directly. Anything on stderr is surfaced when the driver fails. This is the
# integration point for external agent frameworks — wrap any agent CLI in a
# small adapter and point `model:` at it.

def _cmd_complete(cmd: str, messages: list[dict], tools: list[dict],
                  timeout: float, cwd: Optional[str]) -> LLMReply:
    payload = json.dumps({"messages": messages, "tools": tools})
    try:
        r = subprocess.run(cmd, shell=True, input=payload, cwd=cwd,
                           capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"driver timed out after {timeout}s") from e
    if r.returncode != 0:
        raise RuntimeError(f"driver exited {r.returncode}: "
                           f"{r.stderr.strip()[:400]}")
    try:
        out = json.loads(r.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError) as e:
        raise RuntimeError(f"driver returned non-JSON output: "
                           f"{r.stdout.strip()[:200]}") from e
    calls = [
        ToolCall(
            id=str(tc.get("id") or f"cmd-{i}"),
            name=tc["name"],
            arguments=tc.get("arguments") or {},
        )
        for i, tc in enumerate(out.get("tool_calls") or [])
    ]
    return LLMReply(
        content=out.get("content") or "",
        tool_calls=calls,
        input_tokens=int(out.get("input_tokens") or 0),
        output_tokens=int(out.get("output_tokens") or 0),
    )


# ---------------------------------------------------------------- litellm --

# Errors worth retrying — rate limits, connection drops, 5xx. Auth errors,
# bad requests and content-policy refusals fail immediately.
_TRANSIENT = ("RateLimitError", "APIConnectionError", "Timeout",
              "InternalServerError", "ServiceUnavailableError")


def _litellm_complete(model: str, temperature: float, seed: Optional[int],
                      messages: list[dict], tools: Optional[list[dict]],
                      timeout: float, max_retries: int) -> LLMReply:
    try:
        import litellm  # type: ignore
    except ImportError as e:
        raise RuntimeError(
            "litellm not installed — run `pip install 'skilllab[llm]'` "
            "or set model: mock for offline runs") from e
    kwargs: dict[str, Any] = dict(
        model=model, messages=messages, temperature=temperature,
        timeout=timeout)
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"
    if seed is not None:
        kwargs["seed"] = seed
    transient = tuple(cls for n in _TRANSIENT
                      if isinstance((cls := getattr(litellm, n, None)), type))
    for attempt in range(max_retries + 1):
        try:
            resp = litellm.completion(**kwargs)
            break
        except transient:
            if attempt >= max_retries:
                raise
            time.sleep(min(2 ** attempt * 2, 30))
    msg = resp.choices[0].message
    calls = [
        ToolCall(
            id=tc.id,
            name=tc.function.name,
            arguments=json.loads(tc.function.arguments or "{}"),
        )
        for tc in (msg.tool_calls or [])
    ]
    usage = getattr(resp, "usage", None)
    return LLMReply(
        content=msg.content or "",
        tool_calls=calls,
        input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
        output_tokens=getattr(usage, "completion_tokens", 0) or 0,
    )


# ------------------------------------------------------------------- mock --

_WORDS = re.compile(r"[a-zA-ZÀ-ỹ0-9]{4,}")

# Generic words carry no trigger signal — ignoring them keeps the mock's
# activation heuristic roughly honest.
_STOPWORDS = {
    "use", "when", "user", "asks", "asked", "with", "write", "improve",
    "help", "helps", "make", "create", "update", "task", "file", "code",
    "this", "that", "from", "into", "your", "have", "will", "would",
    "could", "should", "also", "them", "then", "than", "please",
}


def _desc_keywords(system_prompt: str) -> dict[str, set[str]]:
    """Extract skill names + keywords from the '## Available skills' listing."""
    skills: dict[str, set[str]] = {}
    in_listing = False
    for line in system_prompt.splitlines():
        if line.startswith("## "):
            in_listing = line.startswith("## Available skills")
            continue
        if in_listing and line.startswith("- "):
            name, _, desc = line[2:].partition(":")
            name = name.strip()
            if name:
                skills[name] = {w.lower() for w in _WORDS.findall(desc)
                                } - _STOPWORDS
    return skills


def _calls(messages: list[dict], name: str) -> list[dict]:
    """Arguments of every prior tool call with the given name."""
    out = []
    for m in messages:
        for tc in m.get("tool_calls") or []:
            if tc["function"]["name"] == name:
                out.append(json.loads(tc["function"]["arguments"] or "{}"))
    return out


def _mock_complete(messages: list[dict], tools: list[dict]) -> LLMReply:
    system = next((m["content"] for m in messages if m["role"] == "system"), "")
    user = next((m["content"] for m in reversed(messages)
                 if m["role"] == "user"), "")
    n = len([m for m in messages if m.get("role") == "tool"])
    call_id = 0

    def call(name: str, args: dict) -> LLMReply:
        nonlocal call_id
        call_id += 1
        return LLMReply(tool_calls=[ToolCall(f"mock-{n}-{call_id}", name, args)])

    # Done once OUTPUT.md exists — reply with a final message, no tool calls.
    if _calls(messages, "write_file"):
        return LLMReply(content="Done — wrote OUTPUT.md with the result.")

    # Follow a resources/ link surfaced by a skill we already activated.
    last_tool = next((m for m in reversed(messages)
                      if m.get("role") == "tool"), None)
    if last_tool and "resources/" in last_tool.get("content", ""):
        skill_reads = _calls(messages, "read_skill")
        m = re.search(r"resources/[\w./-]+", last_tool["content"])
        if skill_reads and m and not _calls(messages, "read_skill_file"):
            return call("read_skill_file",
                        {"name": skill_reads[-1]["name"], "path": m.group(0)})

    # First turn: activate a listed skill whose description keywords overlap
    # the task prompt; otherwise go straight to work.
    if n == 0:
        user_words = {w.lower() for w in _WORDS.findall(user)} - _STOPWORDS
        for name, kw in _desc_keywords(system).items():
            if kw & user_words:
                return call("read_skill", {"name": name})
    return call("write_file", {"path": "OUTPUT.md", "content": _out(user)})


def _out(user: str) -> str:
    head = " ".join(user.split())[:120]
    return f"# Mock agent output\n\nTask: {head}\n\nResult: completed (simulated).\n"
