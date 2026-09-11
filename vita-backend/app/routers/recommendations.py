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

    # ── GUARD: Midday meal prompt must NEVER trigger if user has logged any meal today ──
    if payload.rule_id == "time.midday_meal_prompt":
        from app.models.meal import Meal
        today_meals_count = (
            db.query(Meal)
            .filter(
                Meal.user_id == current_user.id,
                Meal.logged_at >= today_start,
            )
            .count()
        )
        if today_meals_count > 0:
            # User has already logged meal(s) today! Skip creating new prompts.
            # Do NOT delete historical prompt if it was legitimately triggered earlier today.
            existing = (
                db.query(Recommendation)
                .filter(
                    Recommendation.user_id == current_user.id,
                    Recommendation.rule_id == "time.midday_meal_prompt",
                    Recommendation.created_at >= today_start,
                )
                .first()
            )
            if existing:
                return existing

            latest = (
                db.query(Recommendation)
                .filter(Recommendation.user_id == current_user.id)
                .order_by(Recommendation.created_at.desc())
                .first()
            )
            if latest:
                return latest
            return Recommendation(
                id=0,
                user_id=current_user.id,
                type="nutrition",
                severity="info",
                tier="primary_action",
                rule_id="time.midday_meal_prompt_skipped",
                title="Meals Logged",
                message="Meals already logged today",
                is_read=True,
                created_at=now_naive,
            )

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

    # Once ANY new insight triggers, permanently retire the first-time user onboarding insight
    if payload.rule_id != "lifestyle.set_daily_targets":
        db.query(Recommendation).filter(
            Recommendation.user_id == current_user.id,
            Recommendation.rule_id == "lifestyle.set_daily_targets",
            Recommendation.is_read == False,
        ).update({"is_read": True}, synchronize_session=False)

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
    days: int = 30,
):
    """
    Returns all recommendations for the authenticated user, ordered newest first.
    Accepts optional ?days=N query param to limit history window (default: 30 days).
    """
    now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
    today_start_dt = datetime.combine(now_naive.date(), datetime.min.time())

    # If no recommendations exist for today yet, automatically generate them
    today_count = (
        db.query(Recommendation)
        .filter(Recommendation.user_id == current_user.id, Recommendation.created_at >= today_start_dt)
        .count()
    )
    if today_count == 0:
        generate_and_persist_recommendations(current_user.id, db)

    cutoff_dt = now_naive - timedelta(days=days)

    return (
        db.query(Recommendation)
        .filter(
            Recommendation.user_id == current_user.id,
            Recommendation.created_at >= cutoff_dt,
        )
        .order_by(Recommendation.created_at.desc())
        .limit(200)
        .all()
    )


@router.get("/top", response_model=Optional[RecommendationOut])
def get_top_recommendation(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Returns the single active insight for the dashboard.
    Precedence:
      1. Active unread Safety Alert (pinned until read/acknowledged)
      2. Most recently triggered insight for today (latest insight replaces previous ones)
      3. Fallback: Good Morning insight / daily wellness insight
      4. First-time user onboarding (retired permanently once any other insight triggers)
    """
    now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
    today_start = now_naive.date()
    today_start_dt = datetime.combine(today_start, datetime.min.time())

    # 1. Pinned Critical Alert: Check for any unread Safety Alert in the past 48 hours
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

    # 2. Today's Insights (Newest first)
    today_recs = (
        db.query(Recommendation)
        .filter(Recommendation.user_id == current_user.id, Recommendation.created_at >= today_start_dt)
        .order_by(Recommendation.created_at.desc())
        .all()
    )

    from app.models.meal import Meal
    today_meals_count = (
        db.query(Meal)
        .filter(Meal.user_id == current_user.id, Meal.logged_at >= today_start_dt)
        .count()
    )
    if today_meals_count > 0:
        today_recs = [r for r in today_recs if r.rule_id != "time.midday_meal_prompt"]

    # If any regular insight exists today, permanently retire the new user onboarding insight
    if any(r.rule_id != "lifestyle.set_daily_targets" for r in today_recs):
        today_recs = [r for r in today_recs if r.rule_id != "lifestyle.set_daily_targets"]

    if not today_recs:
        # Check if brand-new user with zero prior insights who needs target configuration
        total_history_count = (
            db.query(Recommendation)
            .filter(
                Recommendation.user_id == current_user.id,
                Recommendation.rule_id != "lifestyle.set_daily_targets",
            )
            .count()
        )
        has_targets = current_user.daily_calorie_target is not None
        if total_history_count == 0 and not has_targets:
            # Check if set_daily_targets is unread and not dismissed
            onboarding_rec = (
                db.query(Recommendation)
                .filter(
                    Recommendation.user_id == current_user.id,
                    Recommendation.rule_id == "lifestyle.set_daily_targets",
                    Recommendation.is_read == False,
                )
                .first()
            )
            if onboarding_rec:
                return onboarding_rec

        # Otherwise synthesize today's recommendations
        today_recs = generate_and_persist_recommendations(current_user.id, db)
        if today_meals_count > 0 and today_recs:
            today_recs = [r for r in today_recs if r.rule_id != "time.midday_meal_prompt"]
        if any(r.rule_id != "lifestyle.set_daily_targets" for r in today_recs):
            today_recs = [r for r in today_recs if r.rule_id != "lifestyle.set_daily_targets"]

    if not today_recs:
        # Fall back to the most recent recommendation in history
        return (
            db.query(Recommendation)
            .filter(
                Recommendation.user_id == current_user.id,
                Recommendation.rule_id != "lifestyle.set_daily_targets",
            )
            .order_by(Recommendation.created_at.desc())
            .first()
        )

    # 2. Most recently triggered insight for today takes the dashboard!
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
        .filter(
            Recommendation.user_id == current_user.id,
            # Filter to today's cards so stale cards from previous days don't
            # show up as "active" in the grouped view (BUG-8 fix).
            # Fall back to a 48-hour window in case today's generation hasn't run yet.
            Recommendation.created_at >= datetime.combine(today_start, datetime.min.time()) - timedelta(hours=48),
        )
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


