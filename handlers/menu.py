from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from keyboards.inline import main_menu_keyboard
from utils.filters import AdminFilter

router = Router()
router.message.filter(AdminFilter())
router.callback_query.filter(AdminFilter())


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "🤖 <b>Boshqaruv paneli</b>\n\nBo'limni tanlang:",
        reply_markup=main_menu_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "menu_main")
async def cb_main_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "🤖 <b>Boshqaruv paneli</b>\n\nBo'limni tanlang:",
        reply_markup=main_menu_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()
