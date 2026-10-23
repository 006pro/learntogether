import pytest
from sqlalchemy import select

from app.models import Topic, User
from tests.conftest import add_topic, login, vote


def test_create_topic(client, db):
    token = login(client)
    response = add_topic(client, token, "  Rust   for   beginners ")

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Rust for beginners"
    assert body["vote_count"] == 0
    assert body["has_voted"] is False

    topic = db.scalar(select(Topic))
    creator = db.scalar(select(User))
    assert topic.normalized_name == "rust for beginners"
    assert topic.created_by == creator.id


@pytest.mark.parametrize(
    ("name", "message"),
    [
        ("", "Topic can't be empty."),
        ("   \t\n ", "Topic can't be empty."),
        ("x" * 101, "Topic must be 100 characters or fewer."),
        ("???", "Topic must contain at least one letter or number."),
        ("bad\x00name", "Topic contains invalid characters."),
    ],
)
def test_rejects_invalid_topics(client, name, message):
    token = login(client)
    response = add_topic(client, token, name)
    assert response.status_code == 422
    assert response.json()["detail"] == message


def test_accepts_topic_at_max_length(client):
    token = login(client)
    assert add_topic(client, token, "x" * 100).status_code == 201


@pytest.mark.parametrize("payload", [{}, {"name": None}, {"name": 42}, {"name": "ok", "extra": 1}])
def test_rejects_malformed_payload(client, payload):
    token = login(client)
    response = client.post("/api/topics", json=payload, headers={"X-CSRF-Token": token})
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], str)


@pytest.mark.parametrize("duplicate", ["machine learning", "MACHINE LEARNING", "  Machine   Learning  "])
def test_prevents_duplicate_topics(client, duplicate):
    token = login(client)
    assert add_topic(client, token, "Machine Learning").status_code == 201

    response = add_topic(client, token, duplicate)
    assert response.status_code == 409
    assert response.json()["detail"] == "“Machine Learning” is already on the list."
    assert len(client.get("/api/topics").json()) == 1


def test_duplicate_by_another_user_is_rejected(client, other_client):
    assert add_topic(client, login(client, "Ada"), "Go").status_code == 201
    assert add_topic(other_client, login(other_client, "Grace"), "go").status_code == 409


def test_list_empty(client):
    response = client.get("/api/topics")
    assert response.status_code == 200
    assert response.json() == []


def test_list_counts_and_ordering(client, other_client):
    ada = login(client, "Ada")
    grace = login(other_client, "Grace")

    first = add_topic(client, ada, "Docker").json()
    second = add_topic(client, ada, "Kubernetes").json()
    third = add_topic(other_client, grace, "Terraform").json()

    # Terraform: 2 votes, Kubernetes: 1 vote, Docker: 0 votes.
    assert vote(client, ada, third["id"]).status_code == 201
    assert vote(other_client, grace, third["id"]).status_code == 201
    assert vote(other_client, grace, second["id"]).status_code == 201

    topics = client.get("/api/topics").json()
    assert [(t["name"], t["vote_count"]) for t in topics] == [
        ("Terraform", 2),
        ("Kubernetes", 1),
        ("Docker", 0),
    ]
    # has_voted reflects the session making the request.
    assert {t["name"]: t["has_voted"] for t in topics} == {
        "Terraform": True,
        "Kubernetes": False,
        "Docker": False,
    }
    grace_view = {t["name"]: t["has_voted"] for t in other_client.get("/api/topics").json()}
    assert grace_view == {"Terraform": True, "Kubernetes": True, "Docker": False}
    assert first["id"] != second["id"]


def test_ties_are_ordered_by_creation(client):
    token = login(client)
    names = ["Zig", "Elixir", "Ada language"]
    for name in names:
        add_topic(client, token, name)
    assert [t["name"] for t in client.get("/api/topics").json()] == names


def test_list_is_readable_without_signing_in(client, other_client):
    token = login(client)
    topic = add_topic(client, token, "SQL").json()
    vote(client, token, topic["id"])

    topics = other_client.get("/api/topics").json()
    assert topics == [
        {**topics[0], "name": "SQL", "vote_count": 1, "has_voted": False},
    ]
