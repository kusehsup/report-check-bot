from aiogram import Router

from bot.handlers.check import router as check_router

router = Router(name="root")
router.include_router(check_router)
