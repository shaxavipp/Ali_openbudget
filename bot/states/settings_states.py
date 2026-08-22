from aiogram.fsm.state import State, StatesGroup


class GlobalSettingsStates(StatesGroup):
    waiting_vote_price = State()
    waiting_min_withdrawal = State()
    waiting_donat_account = State()
