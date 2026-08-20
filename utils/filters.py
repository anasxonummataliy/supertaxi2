import os
from aiogram.filters import BaseFilter
from aiogram.types import Message, CallbackQuery


class AdminFilter(BaseFilter):
    async def __call__(self, event) -> bool:
        raw = os.getenv("ADMIN_IDS", "")
        admin_ids = [int(x.strip()) for x in raw.split(",") if x.strip().isdigit()]
        if isinstance(event, (Message, CallbackQuery)):
            return event.from_user.id in admin_ids
        return False
