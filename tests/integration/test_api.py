import sys
import os
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Skip entire module if env is not configured
pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def api_client():
    try:
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app, raise_server_exceptions=False)
        return client
    except Exception as e:
        pytest.skip(f"FastAPI test client could not be created: {e}")


class TestHealthEndpoint:
    def test_health_returns_200(self, api_client):
        resp = api_client.get("/api/v1/health")
        assert resp.status_code == 200

    def test_health_has_app_status(self, api_client):
        data = api_client.get("/api/v1/health").json()
        assert "app_status" in data
        assert data["app_status"] == "ok"

    def test_health_has_db_status(self, api_client):
        data = api_client.get("/api/v1/health").json()
        assert "db_status" in data
        # If DB is up, should be "ok"; if not, should be "error" (not a crash)
        assert data["db_status"] in {"ok", "error"}


class TestKPIEndpoint:
    def test_kpis_returns_200(self, api_client):
        resp = api_client.get("/api/v1/kpis")
        # 200 if data exists, 503 if no transactions yet
        assert resp.status_code in {200, 503}

    def test_kpis_schema(self, api_client):
        resp = api_client.get("/api/v1/kpis")
        if resp.status_code == 200:
            data = resp.json()
            required_fields = [
                "total_transactions", "total_volume", "avg_transaction_value",
                "success_rate_pct", "failure_rate_pct"
            ]
            for field in required_fields:
                assert field in data, f"Missing field: {field}"

    def test_rates_sum_to_reasonable_value(self, api_client):
        resp = api_client.get("/api/v1/kpis")
        if resp.status_code == 200:
            data = resp.json()
            total_rate = data["success_rate_pct"] + data["failure_rate_pct"]
            assert total_rate <= 100.1, f"Rates sum to {total_rate} > 100"


class TestTransactionEndpoints:
    def test_list_transactions_200(self, api_client):
        resp = api_client.get("/api/v1/transactions")
        assert resp.status_code == 200

    def test_list_transactions_has_pagination(self, api_client):
        resp = api_client.get("/api/v1/transactions")
        if resp.status_code == 200:
            data = resp.json()
            assert "items" in data
            assert "meta" in data
            meta = data["meta"]
            assert "total" in meta
            assert "page" in meta
            assert "page_size" in meta

    def test_page_size_limit_enforced(self, api_client):
        resp = api_client.get("/api/v1/transactions?page_size=9999")
        assert resp.status_code == 422

    def test_status_filter_works(self, api_client):
        resp = api_client.get("/api/v1/transactions?status=completed")
        if resp.status_code == 200:
            items = resp.json()["items"]
            for item in items:
                assert item["txn_status"] == "completed"

    def test_invalid_transaction_id_returns_404(self, api_client):
        resp = api_client.get("/api/v1/transactions/999999999")
        assert resp.status_code == 404

    def test_pagination_second_page(self, api_client):
        page1 = api_client.get("/api/v1/transactions?page=1&page_size=10").json()
        page2 = api_client.get("/api/v1/transactions?page=2&page_size=10").json()
        if page1.get("meta", {}).get("total", 0) > 10:
            ids1 = {i["transaction_id"] for i in page1.get("items", [])}
            ids2 = {i["transaction_id"] for i in page2.get("items", [])}
            assert ids1.isdisjoint(ids2), "Pages should contain different transactions"


class TestMonthlyTrends:
    def test_trends_returns_list(self, api_client):
        resp = api_client.get("/api/v1/trends/monthly")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_trends_have_required_fields(self, api_client):
        resp = api_client.get("/api/v1/trends/monthly")
        if resp.status_code == 200 and resp.json():
            item = resp.json()[0]
            assert "month" in item
            assert "txn_count" in item
            assert "total_volume" in item

    def test_trends_months_ordered(self, api_client):
        resp = api_client.get("/api/v1/trends/monthly")
        if resp.status_code == 200 and len(resp.json()) > 1:
            months = [item["month"] for item in resp.json()]
            assert months == sorted(months), "Months should be in ascending order"


class TestAnomalyEndpoints:
    def test_anomaly_runs_endpoint(self, api_client):
        resp = api_client.get("/api/v1/anomalies/runs")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_anomalies_has_disclaimer(self, api_client):
        resp = api_client.get("/api/v1/anomalies")
        if resp.status_code == 200:
            data = resp.json()
            assert "disclaimer" in data
            assert "not confirmed" in data["disclaimer"].lower() or \
                   "suspicious" in data["disclaimer"].lower()
