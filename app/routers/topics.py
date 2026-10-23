from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import case, func, literal, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Topic, TopicVote, User
from app.schemas import MeOut, TopicCreate, TopicOut, UserOut, normalize_topic_name
from app.security import get_csrf_token, get_current_user, require_user, require_writer

router = APIRouter(prefix="/api", tags=["topics"])


def query_topics(db: Session, user_id: int | None, topic_id: int | None = None) -> list[TopicOut]:
    vote_count = func.count(TopicVote.id).label("vote_count")
    if user_id is None:
        has_voted = literal(0)
    else:
        has_voted = func.max(case((TopicVote.user_id == user_id, 1), else_=0))

    stmt = (
        select(Topic, vote_count, has_voted.label("has_voted"))
        .outerjoin(TopicVote, TopicVote.topic_id == Topic.id)
        .group_by(Topic.id)
        .order_by(vote_count.desc(), Topic.created_at.asc(), Topic.id.asc())
    )
    if topic_id is not None:
        stmt = stmt.where(Topic.id == topic_id)

    return [
        TopicOut(
            id=topic.id,
            name=topic.name,
            vote_count=count,
            has_voted=bool(voted),
            created_at=topic.created_at,
        )
        for topic, count, voted in db.execute(stmt)
    ]


@router.get("/me", response_model=MeOut)
def read_me(request: Request, user: User = Depends(require_user)) -> MeOut:
    return MeOut(user=UserOut.model_validate(user), csrf_token=get_csrf_token(request))


@router.get("/topics", response_model=list[TopicOut])
def list_topics(
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
) -> list[TopicOut]:
    return query_topics(db, user.id if user else None)


@router.post("/topics", response_model=TopicOut, status_code=status.HTTP_201_CREATED)
def create_topic(
    payload: TopicCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_writer),
) -> TopicOut:
    normalized = normalize_topic_name(payload.name)
    existing = db.scalar(select(Topic).where(Topic.normalized_name == normalized))
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"“{existing.name}” is already on the list.")

    topic = Topic(name=payload.name, normalized_name=normalized, created_by=user.id)
    db.add(topic)
    try:
        db.commit()
    except IntegrityError:
        # Another request created the same topic between our check and insert.
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, f"“{payload.name}” is already on the list.")

    return query_topics(db, user.id, topic.id)[0]


@router.post("/topics/{topic_id}/vote", response_model=TopicOut, status_code=status.HTTP_201_CREATED)
def vote_for_topic(
    topic_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_writer),
) -> TopicOut:
    if db.get(Topic, topic_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That topic doesn't exist.")

    db.add(TopicVote(topic_id=topic_id, user_id=user.id))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "You've already voted for this topic.")

    return query_topics(db, user.id, topic_id)[0]
