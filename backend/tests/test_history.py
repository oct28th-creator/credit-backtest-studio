"""History as a tree, and the diff that reads it.

These tests are written against the failure modes the flat log had, not
against the happy path:

  * a fresh install must return an empty list, never fixtures — the old
    frontend fell back to four invented runs and every number on the page
    looked measured;
  * a resliced run must appear as a *child*, not as an unrelated row;
  * a diff must align by role, because comparing run A's challenger with
    run B's champion is how a reader reaches the opposite conclusion;
  * a run that trips a blocking guardrail must not look the same in the
    list as one that ships.
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core import runs as runs_service


BASE = {"champion": "v2.2", "challenger": "v2.3",
        "sample_id": "consumer_2024q1q2", "sample_size": 50000, "seed": 42}


@pytest.fixture()
def client():
    return TestClient(app)


@pytest.fixture()
def empty_store():
    """History reads the run store; isolate it so order-dependent runs
    from other modules cannot make these assertions pass by accident."""
    saved = dict(runs_service._RUN_STORE)
    runs_service._RUN_STORE.clear()
    yield
    runs_service._RUN_STORE.clear()
    runs_service._RUN_STORE.update(saved)


def _run(client, **patch) -> str:
    cfg = {**BASE, **patch}
    # /run takes the config at the top level; nesting it under "config" is
    # silently accepted and every field falls back to its default, which is
    # how the first version of this test compared two identical runs.
    r = client.post("/api/experiments/run", json=cfg)
    assert r.status_code == 200, r.text
    return r.json()["run_id"]


def test_empty_history_is_empty(client, empty_store):
    assert client.get("/api/history").json() == []
    assert client.get("/api/history/trees").json()["trees"] == []


def test_row_carries_verdict_and_lineage(client, empty_store):
    rid = _run(client)
    rows = client.get("/api/history").json()
    assert len(rows) == 1
    row = rows[0]
    assert row["run_id"] == rid
    assert row["root_run_id"] == rid and row["parent_run_id"] is None
    assert row["verdict"] in ("clean", "warned", "blocked")
    # The verdict is not decoration: whatever it says must be backed by codes.
    if row["verdict"] == "blocked":
        assert row["blocking"]
    if row["verdict"] == "warned":
        assert row["warnings"] and not row["blocking"]
    assert row["manifest_sha"]


def test_reslice_becomes_a_child_not_a_sibling(client, empty_store):
    root = _run(client)
    child = client.post(f"/api/experiments/{root}/reslice",
                        json={"slice_dim": "age_band", "slice_value": "18-25"}).json()["run_id"]
    assert child != root

    trees = client.get("/api/history/trees").json()["trees"]
    assert len(trees) == 1, "one question, one thread"
    tree = trees[0]
    assert tree["root_run_id"] == root
    assert tree["n_runs"] == 2
    ids = [n["run_id"] for n in tree["nodes"]]
    assert ids == [root, child], "a thread reads forward in time"
    assert [n["depth"] for n in tree["nodes"]] == [0, 1]
    assert tree["nodes"][1]["slice"] == {"dim": "age_band", "value": "18-25"}


def test_two_unrelated_runs_are_two_threads(client, empty_store):
    _run(client)
    _run(client, seed=7)
    assert client.get("/api/history/trees").json()["total"] == 2


def test_diff_aligns_by_role(client, empty_store):
    a = _run(client)
    b = _run(client, champion="v2.3", challenger="v2.2")  # roles deliberately swapped
    d = client.get(f"/api/history/diff?a={a}&b={b}").json()

    by_role = {}
    for m in d["metrics"]:
        by_role.setdefault(m["role"], set()).add((m["strategy_a"], m["strategy_b"]))
    # Same role on both sides even though the version strings traded places.
    assert by_role["challenger"] == {("v2.3", "v2.2")}
    assert by_role["champion"] == {("v2.2", "v2.3")}


def test_diff_surfaces_the_input_that_moved(client, empty_store):
    a = _run(client)
    b = _run(client, seed=99)
    d = client.get(f"/api/history/diff?a={a}&b={b}").json()
    fields = {c["field"] for c in d["config_diff"]}
    assert "seed" in fields
    assert not d["same_manifest"]


def test_identical_config_is_flagged_as_identical(client, empty_store):
    a = _run(client)
    b = _run(client)
    d = client.get(f"/api/history/diff?a={a}&b={b}").json()
    assert d["same_manifest"] is True
    # Same inputs must produce the same numbers; a non-zero delta here would
    # be an engine bug, and the note says so rather than inviting a reading.
    assert all(m["delta"] in (0, 0.0, None) for m in d["metrics"])
    assert all(m["better"] is None for m in d["metrics"])


def test_diff_direction_respects_which_way_is_good(client, empty_store):
    a = _run(client)
    b = _run(client, slice_dim="age_band", slice_value="18-25")
    d = client.get(f"/api/history/diff?a={a}&b={b}").json()
    for m in d["metrics"]:
        if m["delta"] is None or m["better"] is None:
            continue
        if m["key"] in ("ks", "auc", "raroc", "di_min"):
            assert m["better"] == ("b" if m["delta"] > 0 else "a")
        if m["key"] in ("el", "m12_bad", "fpd", "brier"):
            assert m["better"] == ("a" if m["delta"] > 0 else "b")


def test_approval_rate_has_no_winner(client, empty_store):
    """More approvals is not better on its own — it is better or worse only
    together with the bad rate. The diff must refuse to crown one."""
    a = _run(client)
    b = _run(client, seed=5)
    d = client.get(f"/api/history/diff?a={a}&b={b}").json()
    apr = [m for m in d["metrics"] if m["key"] == "approval_rate"]
    assert apr and all(m["better"] is None for m in apr)


def test_diff_of_missing_run_is_404(client, empty_store):
    rid = _run(client)
    assert client.get(f"/api/history/diff?a={rid}&b=nope").status_code == 404


def test_filters(client, empty_store):
    _run(client)
    assert len(client.get("/api/history?strategy=v2.3").json()) == 1
    assert client.get("/api/history?strategy=nope").json() == []
    assert client.get("/api/history?sample=nope").json() == []
