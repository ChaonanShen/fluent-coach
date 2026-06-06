import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services.sessions import session_store
from backend.app.services.storage import log_store


@pytest.fixture(autouse=True)
def clear_state() -> None:
    log_store.clear_all()
    session_store.clear()


def test_mistake_books_list_sessions_with_mistakes() -> None:
    client = TestClient(app)
    empty = client.post("/api/sessions", json={"scenario_id": "meeting"}).json()
    created = client.post("/api/sessions", json={"scenario_id": "interview"}).json()
    session_id = created["session"]["id"]

    client.post(
        f"/api/sessions/{session_id}/turns/text",
        json={"text": "I am working in this field since three years."},
    )
    response = client.get("/api/mistake-books")
    include_empty_response = client.get("/api/mistake-books", params={"include_empty": True})

    assert response.status_code == 200
    books = response.json()["books"]
    assert [book["session_id"] for book in books] == [session_id]
    assert books[0]["title"].startswith("Job Interview - ")
    assert books[0]["scenario_name"] == "Job Interview"
    assert books[0]["mistake_count"] == 2
    assert books[0]["grammar_count"] == 1
    assert books[0]["expression_count"] == 1
    assert books[0]["pronunciation_count"] == 0
    assert books[0]["lowest_mastery"] == 0.1
    assert {book["session_id"] for book in include_empty_response.json()["books"]} == {
        empty["session"]["id"],
        session_id,
    }


def test_mistake_book_detail_groups_mistakes_by_turn() -> None:
    client = TestClient(app)
    created = client.post("/api/sessions", json={"scenario_id": "interview"}).json()
    session_id = created["session"]["id"]
    turn_response = client.post(
        f"/api/sessions/{session_id}/turns/text",
        json={"text": "I am working in this field since three years."},
    )
    user_turn = turn_response.json()["user_turn"]

    response = client.get(f"/api/mistake-books/{session_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["record"]["session_id"] == session_id
    assert body["record"]["mistake_count"] == 2
    assert len(body["turn_groups"]) == 1
    assert body["turn_groups"][0]["turn"]["id"] == user_turn["id"]
    assert body["turn_groups"][0]["turn"]["text"] == user_turn["text"]
    assert {mistake["turn_id"] for mistake in body["turn_groups"][0]["mistakes"]} == {user_turn["id"]}


def test_mistake_book_detail_rejects_unknown_session() -> None:
    client = TestClient(app)

    response = client.get("/api/mistake-books/not-found")

    assert response.status_code == 404
    assert response.json()["detail"] == "Unknown session"


def test_delete_mistake_book_removes_all_session_mistakes() -> None:
    client = TestClient(app)
    created = client.post("/api/sessions", json={"scenario_id": "interview"}).json()
    session_id = created["session"]["id"]
    client.post(
        f"/api/sessions/{session_id}/turns/text",
        json={"text": "I am working in this field since three years."},
    )

    response = client.delete(f"/api/mistake-books/{session_id}")
    books = client.get("/api/mistake-books").json()["books"]
    detail = client.get(f"/api/mistake-books/{session_id}").json()

    assert response.status_code == 200
    assert response.json()["deleted_count"] == 2
    assert books == []
    assert detail["record"]["mistake_count"] == 0
    assert detail["turn_groups"] == []


def test_delete_mistake_book_is_idempotent_for_empty_session() -> None:
    client = TestClient(app)
    created = client.post("/api/sessions", json={"scenario_id": "meeting"}).json()
    session_id = created["session"]["id"]

    response = client.delete(f"/api/mistake-books/{session_id}")

    assert response.status_code == 200
    assert response.json()["deleted_count"] == 0


def test_bulk_delete_mistake_books_removes_selected_sessions_only() -> None:
    client = TestClient(app)
    first = _create_session_with_mistakes(client, "interview", "I am working in this field since three years.")
    second = _create_session_with_mistakes(client, "interview", "I am working in this field since three years.")
    third = _create_session_with_mistakes(client, "interview", "I am working in this field since three years.")

    response = client.post(
        "/api/mistake-books/delete",
        json={"session_ids": [first, second]},
    )
    remaining_books = client.get("/api/mistake-books").json()["books"]

    assert response.status_code == 200
    assert response.json()["deleted_count"] == 4
    assert [book["session_id"] for book in remaining_books] == [third]


def _create_session_with_mistakes(client: TestClient, scenario_id: str, text: str) -> str:
    created = client.post("/api/sessions", json={"scenario_id": scenario_id}).json()
    session_id = created["session"]["id"]
    client.post(f"/api/sessions/{session_id}/turns/text", json={"text": text})
    return session_id
