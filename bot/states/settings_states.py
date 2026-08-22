from aiogram.fsm.state import State, StatesGroup


class GlobalSettingsStates(StatesGroup):
    waiting_vote_price = State()
    waiting_min_withdrawal = State()
    waiting_donat_account = State()
    waiting_vote_counter = State()


class ReferralSettingsStates(StatesGroup):
    waiting_bonus = State()
    waiting_promo_text = State()
