import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import cloudinary
import cloudinary.uploader
from app.config import settings
from app.database import SessionLocal
from app.models.meal import Meal

def main():
    if not settings.CLOUDINARY_URL:
        print("ERROR: CLOUDINARY_URL is not set in your .env file.")
        print("Please set CLOUDINARY_URL=cloudinary://API_KEY:API_SECRET@CLOUD_NAME in vita-backend/.env")
        sys.exit(1)

    import re
    url = settings.CLOUDINARY_URL.strip()
    m = re.match(r"^cloudinary://([^:]+):([^@]+)@(.+)$", url)
    if m:
        api_key, api_secret, cloud_name = m.groups()
        cloudinary.config(cloud_name=cloud_name, api_key=api_key, api_secret=api_secret, secure=True)
    else:
        os.environ["CLOUDINARY_URL"] = url
        cloudinary.config()

    print(f"Connected to Cloudinary cloud: {cloudinary.config().cloud_name}")

    db = SessionLocal()
    try:
        meals = db.query(Meal).filter(Meal.image_url.like("/uploads/%")).all()
        print(f"Found {len(meals)} meal(s) with local image URLs in database.")

        uploads_dir = Path(__file__).resolve().parent / "uploads" / "meals"
        migrated = 0

        for m in meals:
            filename = Path(m.image_url).name
            file_path = uploads_dir / filename
            if not file_path.exists():
                print(f"Skipping meal #{m.id}: local file not found ({file_path})")
                continue

            print(f"Uploading meal #{m.id} ({filename}) to Cloudinary...")
            res = cloudinary.uploader.upload(str(file_path), folder="vitality_meals")
            if res and "secure_url" in res:
                cloud_url = res["secure_url"]
                m.image_url = cloud_url
                migrated += 1
                print(f" -> Success: {cloud_url}")
            else:
                print(f" -> Failed to upload meal #{m.id}")

        if migrated > 0:
            db.commit()
            print(f"\nSuccessfully migrated {migrated} meal image(s) to Cloudinary!")
        else:
            print("\nNo meals needed migration.")
    finally:
        db.close()

if __name__ == "__main__":
    main()
