import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db.session import SessionLocal
from app.core.security import hash_password
from app.models.models import User

print()
print("=" * 45)
print("   Wholesale ERP - Password Reset Tool")
print("=" * 45)
print()

# ── Get inputs ────────────────────────────────
username = input("  Enter username to reset: ").strip()

if not username:
    print("\n  ERROR: Username cannot be empty.")
    input("\n  Press Enter to exit...")
    sys.exit(1)

print()
new_password = input("  Enter new password (min 8 chars): ").strip()

if not new_password:
    print("\n  ERROR: Password cannot be empty.")
    input("\n  Press Enter to exit...")
    sys.exit(1)

if len(new_password) < 8:
    print("\n  ERROR: Password must be at least 8 characters.")
    input("\n  Press Enter to exit...")
    sys.exit(1)

confirm_password = input("  Confirm new password: ").strip()

if new_password != confirm_password:
    print("\n  ERROR: Passwords do not match.")
    input("\n  Press Enter to exit...")
    sys.exit(1)

print()
print(f"  Resetting password for '{username}'...")
print()

# ── Reset in database ─────────────────────────
db = SessionLocal()

try:
    user = db.query(User).filter(User.username == username).first()

    if not user:
        print(f"  ERROR: User '{username}' not found in database.")
        print()
        # Show all users
        all_users = db.query(User).all()
        if all_users:
            print("  Available users:")
            for u in all_users:
                status = "Active" if u.is_active else "Suspended"
                locked = " [LOCKED]" if getattr(u, 'is_locked', False) else ""
                print(f"    - {u.username} ({u.role}) — {status}{locked}")
        print()
        input("  Press Enter to exit...")
        sys.exit(1)

    # Reset password and unlock account
    user.hashed_password = hash_password(new_password)
    user.is_active = True
    user.refresh_token = None

    try:
        user.is_locked = False
        user.failed_login_count = 0
    except Exception:
        pass

    db.commit()

    print("  " + "=" * 41)
    print("   Password reset successfully!")
    print("  " + "=" * 41)
    print()
    print(f"   Username : {user.username}")
    print(f"   Full Name: {user.full_name}")
    print(f"   Role     : {user.role}")
    print(f"   Password : {new_password}")
    print()
    print("   Account has been unlocked and activated.")
    print("   User will need to log in again.")
    print()

except Exception as e:
    db.rollback()
    print(f"  ERROR: {e}")
    print()

finally:
    db.close()

input("  Press Enter to exit...")