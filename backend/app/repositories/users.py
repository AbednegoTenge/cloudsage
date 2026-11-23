from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User


class UserRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_or_create(self, email: str) -> User:
        display = email.split("@", 1)[0].replace(".", " ").title()
        await self.db.execute(
            insert(User)
            .values(email=email, display_name=display, preferences={})
            .on_conflict_do_nothing(index_elements=[User.email])
        )
        return (await self.db.execute(select(User).where(User.email == email))).scalar_one()

    async def update_preferences(self, user: User, display_name: str, preferences: dict) -> User:
        user.display_name = display_name
        user.preferences = preferences
        await self.db.flush()
        return user
