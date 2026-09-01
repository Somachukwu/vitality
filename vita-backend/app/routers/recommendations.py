from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.recommendation import Recommendation
from app.models.user import User
from app.schemas.recommendation import RecommendationCreate, RecommendationOut, RecommendationsGroupedOut
from recommendation_engine.recommendation_service import generate_and_persist_recommendations

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


@router.post("/", response_model=RecommendationOut, status_code=status.HTTP_201_CREATED)
def create_or_log_recommendation(
    payload: RecommendationCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Persists a dynamic or contextual recommendation to the database.
    De-duplicates if the exact same rule_id was already logged today for this user.
    """
    now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
    today_start = datetime.combine(now_naive.date(), datetime.min.time())

    # De-duplicate if same rule_id already logged today for this user
    if payload.rule_id:
        existing = (
            db.query(Recommendation)
            .filter(
                Recommendation.user_id == current_user.id,
                Recommendation.rule_id == payload.rule_id,
                Recommendation.created_at >= today_start,
            )
            .first()
        )
        if existing:
            # Update content if message changed and return existing
            existing.message = payload.message
            existing.title = payload.title
            existing.action_data = payload.action_data
            existing.evidence = payload.evidence
            db.commit()
            db.refresh(existing)
            return existing

    rec = Recommendation(
        user_id=current_user.id,
        type=payload.type,
        severity=payload.severity,
        tier=payload.tier,
        rule_id=payload.rule_id,
        title=payload.title,
        message=payload.message,
        evidence=payload.evidence,
        action_data=payload.action_data,
        expires_at=payload.expires_at,
        created_at=now_naive,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


@router.get("/", response_model=list[RecommendationOut])
def get_recommendations(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Returns all recommendations for the authenticated user, ordered newest first.
    Automatically generates fresh recommendations if none exist for today.
    """
    today_start = datetime.now(timezone.utc).date()
    today_start_dt = datetime.combine(today_start, datetime.min.time())

    today_count = (
        db.query(Recommendation)
        .filter(Recommendation.user_id == current_user.id, Recommendation.created_at >= today_start_dt)
        .count()
    )
    if today_count == 0:
        generate_and_persist_recommendations(current_user.id, db)

    return (
        db.query(Recommendation)
        .filter(Recommendation.user_id == current_user.id)
        .order_by(Recommendation.created_at.desc())
        .limit(50)
        .all()
    )


@router.get("/top", response_model=Optional[RecommendationOut])
def get_top_recommendation(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Returns the single most critical active insight for the dashboard.
    Precedence:
      1. Active unread Safety Alert from today or past 48 hours
      2. Today's Primary Action
      3. Today's Supporting Insight
      4. Most recently created recommendation
    """
    now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
    today_start = now_naive.date()
    today_start_dt = datetime.combine(today_start, datetime.min.time())

    # 1. Check for any unread Safety Alert in the past 48 hours (including yesterday)
    recent_safety = (
        db.query(Recommendation)
        .filter(
            Recommendation.user_id == current_user.id,
            Recommendation.tier == "safety",
            Recommendation.is_read == False,
            Recommendation.created_at >= now_naive - timedelta(days=2),
        )
        .order_by(Recommendation.created_at.desc())
        .first()
    )
    if recent_safety:
        return recent_safety

    today_recs = (
        db.query(Recommendation)
        .filter(Recommendation.user_id == current_user.id, Recommendation.created_at >= today_start_dt)
        .order_by(Recommendation.created_at.desc())
        .all()
    )
    if not today_recs:
        today_recs = generate_and_persist_recommendations(current_user.id, db)

    if not today_recs:
        # Fall back to the most recent recommendation in history
        return (
            db.query(Recommendation)
            .filter(Recommendation.user_id == current_user.id)
            .order_by(Recommendation.created_at.desc())
            .first()
        )

    # 2. Today's Primary Action
    for r in today_recs:
        if r.tier == "primary_action":
            return r

    # 3. Today's Supporting Insight
    for r in today_recs:
        if r.tier == "supporting_insight":
            return r

    # 4. Any today's recommendation (newest first)
    return today_recs[0]



@router.get("/grouped", response_model=RecommendationsGroupedOut)
def get_grouped_recommendations(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Returns recommendations grouped into Safety Alert,
    Primary Action, and Supporting Insight.
    """
    today_start = datetime.now(timezone.utc).date()
    today_start_dt = datetime.combine(today_start, datetime.min.time())

    today_count = (
        db.query(Recommendation)
        .filter(Recommendation.user_id == current_user.id, Recommendation.created_at >= today_start_dt)
        .count()
    )
    if today_count == 0:
        generate_and_persist_recommendations(current_user.id, db)

    recs = (
        db.query(Recommendation)
        .filter(Recommendation.user_id == current_user.id)
        .order_by(Recommendation.created_at.desc())
        .limit(20)
        .all()
    )

    safety = None
    primary = None
    supporting = None

    for r in recs:
        if r.tier == "safety" and safety is None:
            safety = r
        elif r.tier == "primary_action" and primary is None:
            primary = r
        elif r.tier == "supporting_insight" and supporting is None:
            supporting = r

    return RecommendationsGroupedOut(
        safety_alert=safety,
        primary_action=primary,
        supporting_insight=supporting,
        all_active=recs,
    )


@router.post("/generate", response_model=list[RecommendationOut], status_code=status.HTTP_201_CREATED)
def trigger_generation(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Forces on-demand synthesis of fresh recommendations based on latest fused data.
    """
    return generate_and_persist_recommendations(current_user.id, db)


@router.patch("/{rec_id}/read", response_model=RecommendationOut)
def mark_as_read(
    rec_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rec = db.query(Recommendation).filter(
        Recommendation.id == rec_id, Recommendation.user_id == current_user.id
    ).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    rec.is_read = True
    db.commit()
    db.refresh(rec)
    return rec


