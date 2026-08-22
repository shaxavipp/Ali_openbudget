from aiogram import Router

from bot.routers.admin.approval import router as admin_approval_router
from bot.routers.admin.balance_adjust import router as admin_balance_adjust_router
from bot.routers.admin.broadcast import router as admin_broadcast_router
from bot.routers.admin.global_settings import router as admin_global_settings_router
from bot.routers.admin.menu import router as admin_menu_router
from bot.routers.admin.projects import router as admin_projects_router
from bot.routers.admin.referral_settings import router as admin_referral_settings_router
from bot.routers.admin.stats import router as admin_stats_router
from bot.routers.admin.votes_log import router as admin_votes_log_router
from bot.routers.admin.withdrawals_admin import router as admin_withdrawals_router
from bot.routers.user.account import router as user_account_router
from bot.routers.user.info import router as user_info_router
from bot.routers.user.my_votes import router as user_my_votes_router
from bot.routers.user.my_withdrawals import router as user_my_withdrawals_router
from bot.routers.user.referral import router as user_referral_router
from bot.routers.user.start import router as user_start_router
from bot.routers.user.voting import router as user_voting_router
from bot.routers.user.withdrawal import router as user_withdrawal_router

root_router = Router(name="root")

# admin routers first: they're scoped with IsAdmin filters, so ordering here mostly affects
# which handler wins when button text could theoretically collide.
root_router.include_router(admin_approval_router)
root_router.include_router(admin_menu_router)
root_router.include_router(admin_projects_router)
root_router.include_router(admin_global_settings_router)
root_router.include_router(admin_referral_settings_router)
root_router.include_router(admin_balance_adjust_router)
root_router.include_router(admin_broadcast_router)
root_router.include_router(admin_stats_router)
root_router.include_router(admin_votes_log_router)
root_router.include_router(admin_withdrawals_router)

root_router.include_router(user_start_router)
root_router.include_router(user_account_router)
root_router.include_router(user_my_votes_router)
root_router.include_router(user_my_withdrawals_router)
root_router.include_router(user_withdrawal_router)
root_router.include_router(user_referral_router)
root_router.include_router(user_voting_router)
root_router.include_router(user_info_router)
