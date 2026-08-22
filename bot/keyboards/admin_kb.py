from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.callbacks import AdminCancelCB, AdminMenuCB

PANEL_TITLE = "⚙️ Admin panel"


def _cb(section: str) -> str:
    return AdminMenuCB(section=section).pack()


def admin_root_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📢 Xabar yuborish", callback_data=_cb("broadcast")),
                InlineKeyboardButton(text="💳 Balans", callback_data=_cb("balance")),
            ],
            [
                InlineKeyboardButton(text="📁 Loyihalar", callback_data=_cb("projects")),
                InlineKeyboardButton(text="📊 Statistika", callback_data=_cb("stats")),
            ],
            [
                InlineKeyboardButton(text="🗳 Ovozlar", callback_data=_cb("votes")),
                InlineKeyboardButton(text="🧾 Zayafkalar", callback_data=_cb("withdrawals")),
            ],
            [
                InlineKeyboardButton(text="🔗 Referal sozlamalari", callback_data=_cb("referral")),
                InlineKeyboardButton(text="🎛 Global sozlamalar", callback_data=_cb("settings")),
            ],
            [
                InlineKeyboardButton(text="🔄 Botni qayta ishga tushirish", callback_data=_cb("restart")),
            ],
        ]
    )


def restart_confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Ha, qayta ishga tushirish", callback_data=_cb("restart_confirm")
                )
            ],
            [back_button()],
        ]
    )


def back_button() -> InlineKeyboardButton:
    return InlineKeyboardButton(text="« Bosh menyu", callback_data=_cb("root"))


def with_back_row(rows: list[list[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[*rows, [back_button()]])


def cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="« Bekor qilish", callback_data=AdminCancelCB().pack())]
        ]
    )
