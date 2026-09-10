"""
One-off CLI to create (or promote) an admin user.

Admin accounts are deliberately NOT creatable through the public /api/auth/register
endpoint -- that endpoint only ever creates role='user' accounts. This script is
the only way to get an admin account, and it's meant to be run locally by you,
not exposed as an API.

Usage:
    python create_admin.py admin@example.com "a-strong-password"
"""
import sys

from app.database import SessionLocal
from app.models import User, UserRole
from app.security import hash_password


def main():
    if len(sys.argv) != 3:
        print("Usage: python create_admin.py <email> <password>")
        sys.exit(1)

    email, password = sys.argv[1], sys.argv[2]
    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.email == email).first()
        if existing:
            existing.role = UserRole.ADMIN
            existing.password_hash = hash_password(password)
            db.commit()
            print(f"Existing user {email} promoted to admin and password updated.")
        else:
            user = User(email=email, password_hash=hash_password(password), role=UserRole.ADMIN)
            db.add(user)
            db.commit()
            print(f"Admin user {email} created.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
