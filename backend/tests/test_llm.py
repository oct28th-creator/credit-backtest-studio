"""Unit tests for LLM answer post-processing helpers."""
import pytest

from app.services.llm import extract_json_object


def test_plain_json():
    assert extract_json_object('{"findings": ["a"]}') == {"findings": ["a"]}


def test_fenced_json_with_language_tag():
    text = 'Here you go:\n```json\n{"findings": [1, 2]}\n```\nDone.'
    assert extract_json_object(text) == {"findings": [1, 2]}


def test_fenced_json_without_language_tag():
    text = '```\n{"warnings": []}\n```'
    assert extract_json_object(text) == {"warnings": []}


def test_prose_around_bare_object():
    text = 'The result is {"recommendations": ["x"]} as requested.'
    assert extract_json_object(text) == {"recommendations": ["x"]}


def test_first_valid_fenced_block_wins():
    text = '```json\n{"a": 1}\n```\nand also\n```json\n{"b": 2}\n```'
    assert extract_json_object(text) == {"a": 1}


def test_malformed_fence_falls_back_to_bare_object():
    # Broken fenced content, but a valid object exists in the prose
    text = '```json\n{"broken": \n```\nactual answer: {"ok": true}'
    assert extract_json_object(text) == {"ok": True}


def test_json_containing_fence_marker_in_string():
    # A fence marker inside a JSON string must not derail extraction
    text = '{"note": "wrap code in ```json blocks"}'
    assert extract_json_object(text) == {"note": "wrap code in ```json blocks"}


def test_nested_object_with_unicode():
    text = '```json\n{"findings": ["KS 提升 14.3%"], "nested": {"k": "v"}}\n```'
    assert extract_json_object(text) == {"findings": ["KS 提升 14.3%"], "nested": {"k": "v"}}


@pytest.mark.parametrize("bad", ["", "no json here", "[1, 2, 3]", "```json\n[]\n```", "42"])
def test_no_object_raises(bad):
    with pytest.raises(ValueError):
        extract_json_object(bad)
