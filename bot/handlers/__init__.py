from aiogram import Router

from bot.handlers.check import router as check_router
from bot.handlers.panel_auth import router as panel_auth_router
from bot.handlers.skips import router as skips_router

router = Router(name="root")
router.include_router(panel_auth_router)
router.include_router(skips_router)
router.include_router(check_router)
