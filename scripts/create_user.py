import argparse
from passlib.hash import bcrypt
from src.common.db import SessionLocal
from src.models.user import User, RoleEnum

def create_user(username: str, email: str, password: str, admin: bool = False):
    db = SessionLocal()
    try:
        hashed_password = bcrypt.hash(password)  # 👈 хэшируем пароль
        user = User(
            username=username,
            email=email,
            hashed_password=hashed_password,  # 👈 правильное имя поля
            role=RoleEnum.ADMIN if admin else RoleEnum.USER,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        print(f"✅ Пользователь создан: {user.username} ({user.role.value})")
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Создание пользователя")
    parser.add_argument("--username", required=True, help="Имя пользователя")
    parser.add_argument("--email", required=True, help="Email пользователя")
    parser.add_argument("--password", required=True, help="Пароль")
    parser.add_argument("--admin", action="store_true", help="Сделать администратором")
    args = parser.parse_args()

    create_user(args.username, args.email, args.password, args.admin)
