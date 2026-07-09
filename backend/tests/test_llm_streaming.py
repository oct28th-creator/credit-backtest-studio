"""Tests for the real (non-mock) LLM streaming paths in app.services.llm.

The mock branches are exercised by the API tests; here we force
settings.llm_available truthy and script _stream_deepseek / the openai client,
covering: token routing (thinking vs answer), the json_mode retry, error
surfacing as SSE events, and the JSON-extraction fallbacks.
"""
import asyncio
import json
from types import SimpleNamespace

import pytest

from app.services import llm


def collect(agen):
    """Drain an async generator into a list from sync test code."""
    async def _run():
        return [item async for item in agen]
    return asyncio.run(_run())


def sse_events(chunks):
    """Parse SSE-formatted strings into (event, payload) tuples."""
    out = []
    for raw in chunks:
        event = "message"
        payload = None
        for line in raw.strip().splitlines():
            if line.startswith("event:"):
                event = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                payload = json.loads(line.split(":", 1)[1].strip())
        out.append((event, payload))
    return out


@pytest.fixture()
def real_llm(monkeypatch):
    """Force the real (non-mock) branch of every stream_* function."""
    monkeypatch.setattr(llm.settings, "deepseek_api_key", "test-key")
    assert llm.settings.llm_available


def fake_stream(script):
    """Build a _stream_deepseek stand-in yielding the scripted tuples."""
    async def _fake(messages, language="zh", temperature=0.3, json_mode=False):
        for item in script:
            yield item
    return _fake


# ---------------------------------------------------------------------------
# _stream_deepseek (openai client faked)
# ---------------------------------------------------------------------------

def _chunk(content=None, reasoning=None, empty=False):
    if empty:
        return SimpleNamespace(choices=[])
    delta = SimpleNamespace(content=content, reasoning_content=reasoning)
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta)])


class FakeCompletions:
    def __init__(self, chunks, fail_json_mode=False, fail_always=False,
                 explode_mid_stream=False):
        self.chunks = chunks
        self.fail_json_mode = fail_json_mode
        self.fail_always = fail_always
        self.explode_mid_stream = explode_mid_stream
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail_always:
            raise RuntimeError("api unreachable")
        if self.fail_json_mode and "response_format" in kwargs:
            raise RuntimeError("json_object not supported with thinking")

        explode = self.explode_mid_stream

        async def _stream():
            for c in self.chunks:
                yield c
            if explode:
                raise ConnectionError("connection dropped mid-stream")
        return _stream()


def _patch_openai(monkeypatch, completions):
    import openai

    class FakeClient:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=completions)

    monkeypatch.setattr(openai, "AsyncOpenAI", FakeClient)
    return completions


class TestStreamDeepseek:
    def test_routes_thinking_and_answer_tokens(self, monkeypatch):
        comp = _patch_openai(monkeypatch, FakeCompletions([
            _chunk(reasoning="let me think"),
            _chunk(empty=True),  # keep-alive chunk with no choices is skipped
            _chunk(content="hello "),
            _chunk(content="world"),
        ]))
        out = collect(llm._stream_deepseek([{"role": "user", "content": "hi"}]))
        assert out == [("thinking", "let me think"),
                       ("answer", "hello "), ("answer", "world")]
        assert len(comp.calls) == 1

    def test_json_mode_is_requested(self, monkeypatch):
        comp = _patch_openai(monkeypatch, FakeCompletions([_chunk(content="{}")]))
        collect(llm._stream_deepseek([], json_mode=True))
        assert comp.calls[0]["response_format"] == {"type": "json_object"}

    def test_json_mode_rejection_retries_without_it(self, monkeypatch):
        comp = _patch_openai(monkeypatch, FakeCompletions(
            [_chunk(content="ok")], fail_json_mode=True))
        out = collect(llm._stream_deepseek([], json_mode=True))
        assert out == [("answer", "ok")]
        assert len(comp.calls) == 2
        assert "response_format" in comp.calls[0]
        assert "response_format" not in comp.calls[1]

    def test_hard_failure_yields_error_tuple(self, monkeypatch):
        _patch_openai(monkeypatch, FakeCompletions([], fail_always=True))
        out = collect(llm._stream_deepseek([]))
        assert len(out) == 1
        token_type, msg = out[0]
        assert token_type == "error"
        assert "RuntimeError" in msg and "api unreachable" in msg

    def test_mid_stream_failure_yields_error_after_partial(self, monkeypatch):
        _patch_openai(monkeypatch, FakeCompletions(
            [_chunk(content="partial")], explode_mid_stream=True))
        out = collect(llm._stream_deepseek([]))
        assert out[0] == ("answer", "partial")
        assert out[-1][0] == "error"
        assert "ConnectionError" in out[-1][1]


# ---------------------------------------------------------------------------
# stream_analyze_layer (real branch)
# ---------------------------------------------------------------------------

class TestStreamAnalyzeLayer:
    def test_json_answer_becomes_result_event(self, real_llm, monkeypatch):
        answer = json.dumps({"findings": ["f1"], "warnings": ["w1"],
                             "recommendations": ["r1"]})
        monkeypatch.setattr(llm, "_stream_deepseek", fake_stream([
            ("thinking", "analysing..."), ("answer", answer)]))
        events = sse_events(collect(
            llm.stream_analyze_layer("run1", "l1", {"auc": 0.8}, "en")))
        assert events[0] == ("message", {"type": "thinking", "content": "analysing..."})
        result = events[-2][1]
        assert result["findings"] == ["f1"]
        assert result["warnings"] == ["w1"]
        assert events[-1][0] == "done"

    def test_error_tuple_becomes_failure_finding(self, real_llm, monkeypatch):
        monkeypatch.setattr(llm, "_stream_deepseek",
                            fake_stream([("error", "APIError: 500")]))
        events = sse_events(collect(
            llm.stream_analyze_layer("run1", "l1", {}, "en")))
        result = events[0][1]
        assert result["findings"] == ["AI call failed: APIError: 500"]
        assert events[-1][0] == "done"

    def test_unparseable_answer_falls_back_to_insufficient_data(self, real_llm, monkeypatch):
        monkeypatch.setattr(llm, "_stream_deepseek",
                            fake_stream([("answer", "no json here at all")]))
        events = sse_events(collect(
            llm.stream_analyze_layer("run1", "l2", {}, "en")))
        assert events[0][1]["findings"] == ["Insufficient data"]

    def test_zh_error_message(self, real_llm, monkeypatch):
        monkeypatch.setattr(llm, "_stream_deepseek",
                            fake_stream([("error", "timeout")]))
        events = sse_events(collect(
            llm.stream_analyze_layer("run1", "l1", {}, "zh")))
        assert "AI 调用失败" in events[0][1]["findings"][0]


# ---------------------------------------------------------------------------
# stream_parse_config (real branch)
# ---------------------------------------------------------------------------

class TestStreamParseConfig:
    def test_parsed_config_is_emitted(self, real_llm, monkeypatch):
        cfg = {"challenger": "v2.5-RC", "champion": "v2.2"}
        monkeypatch.setattr(llm, "_stream_deepseek", fake_stream([
            ("thinking", "parsing"),
            ("answer", f"```json\n{json.dumps(cfg)}\n```"),
        ]))
        events = sse_events(collect(llm.stream_parse_config("use v2.5", "en")))
        result = next(p for _, p in events if p and p.get("type") == "result")
        assert result["config"]["challenger"] == "v2.5-RC"

    def test_unparseable_answer_falls_back_to_default_config(self, real_llm, monkeypatch):
        monkeypatch.setattr(llm, "_stream_deepseek",
                            fake_stream([("answer", "sorry, no idea")]))
        events = sse_events(collect(llm.stream_parse_config("gibberish", "en")))
        result = next(p for _, p in events if p and p.get("type") == "result")
        assert result["config"]["challenger"] == "v2.3"
        assert result["config"]["champion"] == "v2.2"


# ---------------------------------------------------------------------------
# stream_chat (real branch)
# ---------------------------------------------------------------------------

class TestStreamChat:
    def test_answer_tokens_accumulate_into_single_reply(self, real_llm, monkeypatch):
        monkeypatch.setattr(llm, "_stream_deepseek", fake_stream([
            ("thinking", "hmm"), ("answer", "part one, "), ("answer", "part two")]))
        events = sse_events(collect(
            llm.stream_chat("run1", "why?", [], None, {}, "en")))
        replies = [p for _, p in events if p and p.get("type") == "reply"]
        assert len(replies) == 1
        assert replies[0]["content"] == "part one, part two"

    def test_error_is_embedded_in_reply(self, real_llm, monkeypatch):
        monkeypatch.setattr(llm, "_stream_deepseek",
                            fake_stream([("error", "boom")]))
        events = sse_events(collect(
            llm.stream_chat("run1", "why?", [], None, {}, "en")))
        replies = [p for _, p in events if p and p.get("type") == "reply"]
        assert "AI call failed: boom" in replies[0]["content"]

    def test_history_is_capped_and_sanitised(self, real_llm, monkeypatch):
        captured = {}

        async def _capture(messages, language="zh", temperature=0.3, json_mode=False):
            captured["messages"] = messages
            yield ("answer", "ok")

        monkeypatch.setattr(llm, "_stream_deepseek", _capture)
        history = ([{"role": "user", "content": f"turn {i}"} for i in range(12)]
                   + [{"role": "system", "content": "injected"},
                      {"role": "user", "content": ""}])
        collect(llm.stream_chat("run1", "q", history, "l1", {}, "en"))
        msgs = captured["messages"]
        # system prompt + at most 8 history turns + the new user message
        assert len(msgs) <= 10
        assert all(m["role"] != "system" for m in msgs[1:])  # injected role dropped
        assert msgs[-1]["content"] == "q"


# ---------------------------------------------------------------------------
# stream_report / stream_compare_strategies (real branches)
# ---------------------------------------------------------------------------

class TestStreamReport:
    def test_answer_tokens_stream_as_chunks(self, real_llm, monkeypatch):
        monkeypatch.setattr(llm, "_stream_deepseek", fake_stream([
            ("thinking", "outlining"), ("answer", "# Report\n"), ("answer", "body")]))
        events = sse_events(collect(llm.stream_report("run1", {}, "en")))
        chunks = [p["content"] for _, p in events if p and p.get("type") == "chunk"]
        assert chunks == ["# Report\n", "body"]
        assert events[-1][0] == "done"

    def test_error_becomes_visible_chunk(self, real_llm, monkeypatch):
        monkeypatch.setattr(llm, "_stream_deepseek",
                            fake_stream([("error", "rate limited")]))
        events = sse_events(collect(llm.stream_report("run1", {}, "en")))
        chunks = [p["content"] for _, p in events if p and p.get("type") == "chunk"]
        assert any("AI call failed: rate limited" in c for c in chunks)


class TestStreamCompare:
    def test_result_event_from_json_answer(self, real_llm, monkeypatch):
        answer = json.dumps({"findings": ["cutoff relaxed"], "warnings": [],
                             "recommendations": ["verify L3"]})
        monkeypatch.setattr(llm, "_stream_deepseek", fake_stream([("answer", answer)]))
        events = sse_events(collect(llm.stream_compare_strategies({}, "en")))
        result = events[0][1]
        assert result["findings"] == ["cutoff relaxed"]
        assert result["recommendations"] == ["verify L3"]

    def test_error_path(self, real_llm, monkeypatch):
        monkeypatch.setattr(llm, "_stream_deepseek",
                            fake_stream([("error", "503")]))
        events = sse_events(collect(llm.stream_compare_strategies({}, "en")))
        assert events[0][1]["findings"] == ["AI call failed: 503"]

    def test_unparseable_answer_falls_back(self, real_llm, monkeypatch):
        monkeypatch.setattr(llm, "_stream_deepseek",
                            fake_stream([("answer", "prose only")]))
        events = sse_events(collect(llm.stream_compare_strategies({}, "en")))
        assert events[0][1]["findings"] == ["Insufficient data"]
