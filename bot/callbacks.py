from typing import Literal

from aiogram.filters.callback_data import CallbackData


class VoteDecisionCB(CallbackData, prefix="votedec"):
    vote_id: int
    action: Literal["approve", "reject"]


class AdminMenuCB(CallbackData, prefix="adm"):
    section: Literal[
        "root",
        "broadcast",
        "balance",
        "projects",
        "stats",
        "votes",
        "referral",
        "withdrawals",
        "settings",
        "restart",
        "restart_confirm",
    ]


class AdminCancelCB(CallbackData, prefix="admcancel"):
    """Cancels whatever admin FSM flow is active and returns to the root panel."""


class ProjectActionCB(CallbackData, prefix="proj"):
    project_id: int
    action: Literal[
        "view",
        "rename",
        "set_url",
        "set_target_menu",
        "set_target_number",
        "set_target_unlimited",
        "move_up",
        "move_down",
        "activate",
        "delete",
        "delete_confirm",
        "back",
    ]


class StatsPeriodCB(CallbackData, prefix="stats"):
    period: Literal["today", "yesterday", "week", "month", "custom", "all"]


class PageCB(CallbackData, prefix="page"):
    scope: Literal["votes", "withdrawals"]
    offset: int


class WithdrawalActionCB(CallbackData, prefix="wd"):
    withdrawal_id: int
    action: Literal["mark_paid"]


class MyVotesCB(CallbackData, prefix="myv"):
    status: Literal["all", "confirmed", "pending", "rejected"]
    offset: int


class MyWithdrawalsCB(CallbackData, prefix="mywd"):
    offset: int
