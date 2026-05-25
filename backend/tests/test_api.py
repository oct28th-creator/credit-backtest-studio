"""
API endpoint tests using FastAPI TestClient.
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


# ---------------------------------------------------------------------------
# Health checks
# ---------------------------------------------------------------------------

class TestHealthCheck:
    def test_root_health_returns_200(self):
        response = client.get("/")
        assert response.status_code == 200

    def test_root_health_body(self):
        response = client.get("/")
        data = response.json()
        assert data["status"] == "ok"
        assert data["app"] == "BackTest Studio"
        assert "version" in data
        assert "llm_available" in data

    def test_api_health_returns_200(self):
        response = client.get("/api/health")
        assert response.status_code == 200

    def test_api_health_body(self):
        response = client.get("/api/health")
        data = response.json()
        assert data["status"] == "ok"
        assert "llm_available" in data
        assert "cors_origins" in data


# ---------------------------------------------------------------------------
# Samples endpoints
# ---------------------------------------------------------------------------

class TestSamplesEndpoints:
    def test_list_samples_returns_200(self):
        response = client.get("/api/samples")
        assert response.status_code == 200

    def test_list_samples_returns_list(self):
        response = client.get("/api/samples")
        data = response.json()
        assert "samples" in data
        assert isinstance(data["samples"], list)
        assert data["total"] == 2

    def test_list_samples_has_required_fields(self):
        response = client.get("/api/samples")
        samples = response.json()["samples"]
        for s in samples:
            assert "id" in s
            assert "name_zh" in s
            assert "name_en" in s
            assert "n_rows" in s

    def test_list_strategies_returns_200(self):
        response = client.get("/api/samples/strategies")
        assert response.status_code == 200

    def test_list_strategies_has_four_strategies(self):
        response = client.get("/api/samples/strategies")
        data = response.json()
        assert "strategies" in data
        assert data["total"] == 4

    def test_strategies_include_defaults(self):
        response = client.get("/api/samples/strategies")
        data = response.json()
        assert "defaults" in data
        defaults = data["defaults"]
        assert defaults["challenger"] == "v2.3"
        assert defaults["champion"] == "v2.2"

    def test_strategies_have_rules(self):
        response = client.get("/api/samples/strategies")
        strategies = response.json()["strategies"]
        for s in strategies:
            assert "rules" in s
            rules = s["rules"]
            assert "anti_fraud_rules" in rules
            assert "if_else" in rules
            assert "scorecard_features" in rules


# ---------------------------------------------------------------------------
# Experiments endpoints
# ---------------------------------------------------------------------------

class TestExperimentsRun:
    def test_run_default_config_returns_200(self):
        payload = {
            "challenger": "v2.3",
            "champion": "v2.2",
            "beta": "v2.4-Beta",
            "sample_id": "consumer_2024q1q2",
            "lookback_months": 6,
            "perf_window_months": 12,
            "ri_mode": "parceling",
            "language": "zh",
        }
        response = client.post("/api/experiments/run", json=payload)
        assert response.status_code == 200

    def test_run_returns_run_result_schema(self):
        payload = {
            "challenger": "v2.3",
            "champion": "v2.2",
            "sample_id": "consumer_2024q1q2",
            "language": "zh",
        }
        response = client.post("/api/experiments/run", json=payload)
        data = response.json()
        assert "run_id" in data
        assert "champion" in data
        assert "challenger" in data
        assert "sample_size" in data
        assert "duration_s" in data
        assert "snapshot_sha" in data
        assert "layers" in data
        assert "config" in data

    def test_run_without_beta(self):
        payload = {
            "challenger": "v2.3",
            "champion": "v2.2",
            "beta": None,
            "sample_id": "consumer_2024q1q2",
            "language": "en",
        }
        response = client.post("/api/experiments/run", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["beta"] is None

    def test_run_with_v25_beta(self):
        payload = {
            "challenger": "v2.3",
            "champion": "v2.2",
            "beta": "v2.5-RC",
            "sample_id": "consumer_2024q1q2",
            "language": "zh",
        }
        response = client.post("/api/experiments/run", json=payload)
        assert response.status_code == 200

    def test_run_invalid_strategy_returns_400(self):
        payload = {
            "challenger": "v99.99",
            "champion": "v2.2",
            "sample_id": "consumer_2024q1q2",
            "language": "zh",
        }
        response = client.post("/api/experiments/run", json=payload)
        assert response.status_code == 400

    def test_run_invalid_beta_returns_400(self):
        payload = {
            "challenger": "v2.3",
            "champion": "v2.2",
            "beta": "invalid-beta",
            "sample_id": "consumer_2024q1q2",
            "language": "zh",
        }
        response = client.post("/api/experiments/run", json=payload)
        assert response.status_code == 400

    def test_run_layers_contain_all_strategies(self):
        payload = {
            "challenger": "v2.3",
            "champion": "v2.2",
            "beta": "v2.4-Beta",
            "sample_id": "consumer_2024q1q2",
            "language": "zh",
        }
        response = client.post("/api/experiments/run", json=payload)
        layers = response.json()["layers"]
        # New structure: keyed by layer (l1-l5), strategies appear inside each layer
        versions = [kpi["version"] for kpi in layers["l1"]["kpis"]]
        assert "v2.2" in versions
        assert "v2.3" in versions
        assert "v2.4-Beta" in versions

    def test_run_layers_contain_l1_through_l5(self):
        payload = {
            "challenger": "v2.3",
            "champion": "v2.2",
            "sample_id": "consumer_2024q1q2",
            "language": "zh",
        }
        response = client.post("/api/experiments/run", json=payload)
        layers = response.json()["layers"]
        for layer in ["l1", "l2", "l3", "l4", "l5"]:
            assert layer in layers

    def test_run_has_strategy_data_in_each_layer(self):
        payload = {
            "challenger": "v2.3",
            "champion": "v2.2",
            "sample_id": "consumer_2024q1q2",
            "language": "zh",
        }
        response = client.post("/api/experiments/run", json=payload)
        layers = response.json()["layers"]
        # l1 kpis is a list of per-strategy objects
        assert isinstance(layers["l1"]["kpis"], list)
        assert len(layers["l1"]["kpis"]) >= 2
        # l5 di_by_group is keyed by strategy id
        for sid in ["v2.2", "v2.3"]:
            assert sid in layers["l5"]["di_by_group"]


class TestExperimentsList:
    @pytest.fixture(autouse=True)
    def create_a_run(self):
        """Ensure at least one run exists."""
        payload = {
            "challenger": "v2.3",
            "champion": "v2.2",
            "sample_id": "consumer_2024q1q2",
            "language": "zh",
        }
        client.post("/api/experiments/run", json=payload)

    def test_list_returns_200(self):
        response = client.get("/api/experiments")
        assert response.status_code == 200

    def test_list_has_runs_key(self):
        response = client.get("/api/experiments")
        data = response.json()
        assert "runs" in data
        assert "total" in data

    def test_list_pagination(self):
        response = client.get("/api/experiments?limit=5&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert data["limit"] == 5

    def test_history_returns_200(self):
        response = client.get("/api/experiments/history")
        assert response.status_code == 200


class TestExperimentsGetById:
    @pytest.fixture
    def run_id(self):
        payload = {
            "challenger": "v2.3",
            "champion": "v2.2",
            "sample_id": "consumer_2024q1q2",
            "language": "zh",
        }
        response = client.post("/api/experiments/run", json=payload)
        return response.json()["run_id"]

    def test_get_existing_run(self, run_id):
        response = client.get(f"/api/experiments/{run_id}")
        assert response.status_code == 200

    def test_get_existing_run_has_layers(self, run_id):
        response = client.get(f"/api/experiments/{run_id}")
        data = response.json()
        assert "layers" in data
        assert "run_id" in data

    def test_get_nonexistent_run_returns_404(self):
        response = client.get("/api/experiments/nonexistent-run-id")
        assert response.status_code == 404


class TestResliceEndpoint:
    @pytest.fixture
    def run(self):
        payload = {
            "challenger": "v2.3",
            "champion": "v2.2",
            "beta": "v2.4-Beta",
            "sample_id": "consumer_2024q1q2",
            "language": "zh",
        }
        return client.post("/api/experiments/run", json=payload).json()

    def test_reslice_returns_200(self, run):
        response = client.post(
            f"/api/experiments/{run['run_id']}/reslice",
            json={"slice_dim": "gender", "slice_value": "female"},
        )
        assert response.status_code == 200

    def test_reslice_reduces_sample_size(self, run):
        full_size = run["sample_size"]
        response = client.post(
            f"/api/experiments/{run['run_id']}/reslice",
            json={"slice_dim": "gender", "slice_value": "female"},
        )
        sliced = response.json()
        assert sliced["sample_size"] < full_size
        # female ~42% of the population
        assert 0.30 * full_size <= sliced["sample_size"] <= 0.52 * full_size

    def test_reslice_recomputes_layers(self, run):
        response = client.post(
            f"/api/experiments/{run['run_id']}/reslice",
            json={"slice_dim": "gender", "slice_value": "female"},
        )
        data = response.json()
        for layer in ["l1", "l2", "l3", "l4", "l5"]:
            assert layer in data["layers"]

    def test_reslice_updates_store(self, run):
        client.post(
            f"/api/experiments/{run['run_id']}/reslice",
            json={"slice_dim": "gender", "slice_value": "female"},
        )
        refetched = client.get(f"/api/experiments/{run['run_id']}").json()
        assert refetched["sample_size"] < run["sample_size"]
        assert refetched["config"]["slice_dim"] == "gender"

    def test_reslice_nonexistent_run_returns_404(self):
        response = client.post(
            "/api/experiments/nonexistent/reslice",
            json={"slice_dim": "gender", "slice_value": "female"},
        )
        assert response.status_code == 404


class TestAIStatusSecurity:
    def test_status_returns_200(self):
        assert client.get("/api/ai/status").status_code == 200

    def test_status_does_not_leak_api_key(self):
        data = client.get("/api/ai/status").json()
        # The diagnostic must never expose any fragment of the key.
        assert "api_key_hint" not in data
        assert "api_key" not in data
        assert "deepseek_api_key" not in data
        # Only a boolean presence flag is allowed.
        assert "api_key_present" in data
        assert isinstance(data["api_key_present"], bool)


# ---------------------------------------------------------------------------
# Reports endpoint
# ---------------------------------------------------------------------------

class TestReportsEndpoint:
    @pytest.fixture
    def run_id(self):
        payload = {
            "challenger": "v2.3",
            "champion": "v2.2",
            "beta": "v2.4-Beta",
            "sample_id": "consumer_2024q1q2",
            "language": "zh",
        }
        response = client.post("/api/experiments/run", json=payload)
        return response.json()["run_id"]

    def test_report_zh_returns_200(self, run_id):
        response = client.get(f"/api/reports/{run_id}?language=zh")
        assert response.status_code == 200

    def test_report_en_returns_200(self, run_id):
        response = client.get(f"/api/reports/{run_id}?language=en")
        assert response.status_code == 200

    def test_report_has_content(self, run_id):
        response = client.get(f"/api/reports/{run_id}")
        data = response.json()
        assert "content" in data
        assert len(data["content"]) > 100

    def test_report_markdown_format(self, run_id):
        response = client.get(f"/api/reports/{run_id}?format=markdown")
        data = response.json()
        assert data["format"] == "markdown"
        # Should contain markdown headers
        assert "#" in data["content"]

    def test_report_json_format(self, run_id):
        response = client.get(f"/api/reports/{run_id}?format=json")
        data = response.json()
        assert "summary" in data
        assert "run_id" in data

    def test_report_nonexistent_run_returns_404(self):
        response = client.get("/api/reports/nonexistent")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# AI endpoints (mock mode, no API key)
# ---------------------------------------------------------------------------

class TestAIEndpoints:
    @pytest.fixture
    def run_id(self):
        payload = {
            "challenger": "v2.3",
            "champion": "v2.2",
            "sample_id": "consumer_2024q1q2",
            "language": "zh",
        }
        response = client.post("/api/experiments/run", json=payload)
        return response.json()["run_id"]

    def test_parse_config_stream_returns_200(self):
        payload = {
            "text": "用 v2.3 做 challenger，v2.2 做 champion，加上 v2.4-Beta，用主样本",
            "language": "zh",
        }
        response = client.post("/api/ai/parse-config/stream", json=payload)
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]

    def test_analyze_layer_stream_returns_200(self, run_id):
        response = client.get(f"/api/ai/analyze-layer/stream/{run_id}?layer=l1&language=zh")
        assert response.status_code == 200

    def test_analyze_layer_nonexistent_run_returns_404(self):
        response = client.get("/api/ai/analyze-layer/stream/bad-run-id?layer=l1")
        assert response.status_code == 404

    def test_chat_stream_returns_200(self, run_id):
        payload = {
            "run_id": run_id,
            "message": "v2.3 的 RAROC 是多少？",
            "history": [],
            "layer": "l2",
            "language": "zh",
        }
        response = client.post("/api/ai/chat/stream", json=payload)
        assert response.status_code == 200

    def test_report_stream_returns_200(self, run_id):
        response = client.get(f"/api/ai/report/stream/{run_id}?language=zh")
        assert response.status_code == 200

    def test_compare_stream_returns_200(self, run_id):
        response = client.post(f"/api/ai/compare/stream?run_id={run_id}&language=zh")
        assert response.status_code == 200
