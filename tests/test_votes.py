import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.models import TopicVote, User
from tests.conftest import add_topic, login, vote


def test_vote_once(client):
    token = login(client)
    topic = add_topic(client, token, "Statistics").json()

    response = vote(client, token, topic["id"])
    assert response.status_code == 201
    assert response.json()["vote_count"] == 1
    assert response.json()["has_voted"] is True


def test_duplicate_vote_rejected(client, db):
    token = login(client)
    topic = add_topic(client, token, "Statistics").json()
    assert vote(client, token, topic["id"]).status_code == 201

    response = vote(client, token, topic["id"])
    assert response.status_code == 409
    assert response.json()["detail"] == "You've already voted for this topic."
    assert db.scalar(select(func.count(TopicVote.id))) == 1


def test_unique_constraint_enforced_by_database(client, db):
    token = login(client)
    topic = add_topic(client, token, "Statistics").json()
    user_id = db.scalar(select(User.id))

    db.add(TopicVote(topic_id=topic["id"], user_id=user_id))
    db.commit()
    db.add(TopicVote(topic_id=topic["id"], user_id=user_id))
    with pytest.raises(IntegrityError):
        db.commit()


def test_foreign_keys_enforced_by_database(client, db):
    login(client)
    user_id = db.scalar(select(User.id))
    db.add(TopicVote(topic_id=9999, user_id=user_id))
    with pytest.raises(IntegrityError):
        db.commit()


def test_different_users_can_vote_for_same_topic(client, other_client):
    ada = login(client, "Ada")
    grace = login(other_client, "Grace")
    topic = add_topic(client, ada, "Compilers").json()

    assert vote(client, ada, topic["id"]).status_code == 201
    response = vote(other_client, grace, topic["id"])
    assert response.status_code == 201
    assert response.json()["vote_count"] == 2


def test_creating_topic_does_not_vote(client):
    token = login(client)
    topic = add_topic(client, token, "Compilers").json()
    assert topic["vote_count"] == 0
    # The creator can still vote for their own topic separately.
    assert vote(client, token, topic["id"]).status_code == 201


def test_vote_nonexistent_topic(client):
    token = login(client)
    response = vote(client, token, 12345)
    assert response.status_code == 404
    assert response.json()["detail"] == "That topic doesn't exist."


def test_vote_invalid_topic_id(client):
    token = login(client)
    response = client.post("/api/topics/not-a-number/vote", headers={"X-CSRF-Token": token})
    assert response.status_code == 422
