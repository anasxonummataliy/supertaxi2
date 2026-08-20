from aiogram.fsm.state import State, StatesGroup


class AddAccountStates(StatesGroup):
    waiting_phone = State()
    waiting_code = State()
    waiting_qr_scan = State()
    waiting_2fa = State()


class BroadcastStates(StatesGroup):
    waiting_message = State()
    selecting_accounts = State()
    selecting_groups = State()
    adding_group_username = State()
    selecting_interval = State()
    selecting_stagger = State()


class GroupAddStates(StatesGroup):
    waiting_username = State()
