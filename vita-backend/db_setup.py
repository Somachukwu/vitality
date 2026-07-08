"""
Utility script for database management tasks.

Usage:
    python db_setup.py verify        — list all tables and row counts
    python db_setup.py reset         — DROP and recreate all tables (DESTROYS DATA)
    python db_setup.py seed          — insert sample data for local testing
"""
import sys

from sqlalchemy import inspect, text

from app.database import Base, SessionLocal, engine
from app.models import Device, Meal, MealItem, Recommendation, User, Vitals  # noqa: F401


def verify():
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    print(f"\n{'Table':<20} {'Columns':<10}")
    print("-" * 35)
    for t in sorted(tables):
        cols = inspector.get_columns(t)
        print(f"{t:<20} {len(cols):<10}")
    print(f"\nTotal tables: {len(tables)}\n")


def reset():
    confirm = input("This will DROP all tables. Type 'yes' to confirm: ")
    if confirm.lower() != "yes":
        print("Aborted.")
        return
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    print("All tables dropped and recreated.")


def seed():
    from app.core.security import hash_password
    db = SessionLocal()
    try:
        if db.query(User).filter(User.email == "demo@vita.app").first():
            print("Seed data already exists.")
            return

        user = User(
            name="Demo User",
            email="demo@vita.app",
            password_hash=hash_password("demo1234"),
            age=28,
            sex="male",
            height=175.0,
            weight=72.0,
            daily_calorie_target=2200,
            goal_type="maintenance",
        )
        db.add(user)
        db.flush()

        rec = Recommendation(
            user_id=user.id,
            type="nutrition",
            severity="info",
            title="Welcome to Vita!",
            message="Connect your ESP32 device to start tracking your vitals.",
        )
        db.add(rec)
        db.commit()
        print("Seed complete. Demo login -> email: demo@vita.app  password: demo1234")
    finally:
        db.close()


COMMANDS = {"verify": verify, "reset": reset, "seed": seed}

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "verify"
    if cmd not in COMMANDS:
        print(f"Unknown command '{cmd}'. Options: {', '.join(COMMANDS)}")
        sys.exit(1)
    COMMANDS[cmd]()
