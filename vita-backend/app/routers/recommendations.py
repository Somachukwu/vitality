from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.recommendation import Recommendation
from app.models.user import User
from app.schemas.recommendation import RecommendationOut, RecommendationsGroupedOut
from recommendation_engine.recommendation_service import generate_and_persist_recommendations

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


@router.get("/", response_model=list[RecommendationOut])
def get_recommendations(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Returns the latest recommendations for the authenticated user.
    If no recommendations exist yet, runs generation on-the-fly.
    """
    recs = (
        db.query(Recommendation)
        .filter(Recommendation.user_id == current_user.id)
        .order_by(Recommendation.created_at.desc())
        .limit(20)
        .all()
    )
    if not recs:
        recs = generate_and_persist_recommendations(current_user.id, db)
    return recs


@router.get("/grouped", response_model=RecommendationsGroupedOut)
def get_grouped_recommendations(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Returns curated recommendations grouped into Safety Alert,
    Primary Action, and Supporting Insight.
    """
    recs = (
        db.query(Recommendation)
        .filter(Recommendation.user_id == current_user.id)
        .order_by(Recommendation.created_at.desc())
        .limit(20)
        .all()
    )
    if not recs:
        recs = generate_and_persist_recommendations(current_user.id, db)

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

