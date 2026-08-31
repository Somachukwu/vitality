from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password, verify_password
from app.database import get_db
from app.models.user import User
from app.schemas.user import TokenResponse, UserLogin, UserRegister

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(body: UserRegister, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == body.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    notif_prefs = None
    if body.activity_level:
        notif_prefs = {"targets": {"activity_level": body.activity_level}}

    user = User(
        name=body.name,
        email=body.email,
        password_hash=hash_password(body.password),
        age=body.age,
        sex=body.sex,
        height=body.height,
        goal_type=body.goal_type,
        notification_preferences=notif_prefs,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # Immediately generate initial target-setting recommendation for the new user
    try:
        from recommendation_engine.recommendation_service import generate_and_persist_recommendations
        generate_and_persist_recommendations(user.id, db)
    except Exception:
        pass

    return TokenResponse(
        access_token=create_access_token(user.id),
        user_id=user.id,
        name=user.name,
    )


@router.post("/login", response_model=TokenResponse)
def login(body: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    return TokenResponse(
        access_token=create_access_token(user.id),
        user_id=user.id,
        name=user.name,
    )
