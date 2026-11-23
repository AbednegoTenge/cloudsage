from fastapi.testclient import TestClient

from tests.conftest import BOB, connection_body

BASE = "/api/v1/connections"


def test_create_list_get(api: TestClient, connection: dict):
    assert connection["status"] == "unvalidated"
    assert connection["accountId"] == "123456789012"
    assert connection["allowedRegions"] == ["us-east-1", "us-west-2"]
    assert "secret" not in str(connection).lower()

    listed = api.get(BASE).json()
    assert [c["id"] for c in listed] == [connection["id"]]
    assert api.get(f"{BASE}/{connection['id']}").json()["name"] == "prod-us-east-1"


def test_duplicate_name_conflicts(api: TestClient, connection: dict):
    r = api.post(BASE, json=connection_body())
    assert r.status_code == 409


def test_access_keys_rejected(api: TestClient):
    r = api.post(BASE, json=connection_body(externalId="AKIAIOSFODNN7EXAMPLE"))
    assert r.status_code == 422


def test_validate_marks_connected_in_mock_mode(api: TestClient, connection: dict):
    r = api.post(f"{BASE}/{connection['id']}/validate")
    assert r.status_code == 200
    assert r.json()["status"] == "connected"
    assert r.json()["lastValidatedAt"]


def test_update_resets_validation_when_role_changes(api: TestClient, connection: dict):
    api.post(f"{BASE}/{connection['id']}/validate")
    same_role = api.put(f"{BASE}/{connection['id']}", json=connection_body(name="renamed"))
    assert same_role.json()["status"] == "connected"
    new_role = api.put(
        f"{BASE}/{connection['id']}",
        json=connection_body(roleArn="arn:aws:iam::123456789012:role/Other"),
    )
    assert new_role.status_code == 200
    assert new_role.json()["status"] == "unvalidated"
    assert new_role.json()["lastValidatedAt"] is None


def test_soft_delete_hides_connection_and_frees_name(api: TestClient, connection: dict):
    assert api.delete(f"{BASE}/{connection['id']}").status_code == 204
    assert api.get(f"{BASE}/{connection['id']}").status_code == 404
    assert api.get(BASE).json() == []
    assert api.post(BASE, json=connection_body()).status_code == 201


def test_unknown_and_malformed_ids_are_404(api: TestClient):
    assert api.get(f"{BASE}/not-a-uuid").status_code == 404
    assert api.get(f"{BASE}/00000000-0000-0000-0000-000000000000").status_code == 404


def test_users_cannot_see_each_others_connections(api: TestClient, connection: dict):
    bob = {"X-CloudSage-User": BOB}
    assert api.get(BASE, headers=bob).json() == []
    cid = connection["id"]
    assert api.get(f"{BASE}/{cid}", headers=bob).status_code == 404
    assert api.put(f"{BASE}/{cid}", json=connection_body(), headers=bob).status_code == 404
    assert api.post(f"{BASE}/{cid}/validate", headers=bob).status_code == 404
    assert api.delete(f"{BASE}/{cid}", headers=bob).status_code == 404
    # Bob may reuse the same name in his own namespace.
    assert api.post(BASE, json=connection_body(), headers=bob).status_code == 201
