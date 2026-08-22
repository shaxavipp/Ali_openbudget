from urllib.parse import urlparse

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.callbacks import AdminMenuCB, ProjectActionCB
from bot.filters import IsAdmin
from bot.keyboards import admin_kb
from bot.states.project_states import ProjectCreateStates, ProjectEditStates
from db.models.project import Project
from repositories import project_repo
from services import project_service

router = Router(name="admin_projects")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())

ADD_PROJECT_CB = "proj_add_start"
TARGET_NUMBER_CB = "proj_new_target:number"
TARGET_UNLIMITED_CB = "proj_new_target:unlimited"

# Loyiha havolasi shu domen (yoki uning istalgan subdomeni: new.openbudget.uz,
# www.openbudget.uz va h.k.) ostida bo'lishi kerak.
BOARD_URL_DOMAIN = "openbudget.uz"
BOARD_URL_HINT = "❗ Havola openbudget.uz saytiga tegishli bo'lishi kerak. Qayta kiriting:"


def _is_valid_board_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        return False
    host = parsed.hostname.lower()
    return host == BOARD_URL_DOMAIN or host.endswith(f".{BOARD_URL_DOMAIN}")


def _target_choice_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔢 Son kiritish", callback_data=TARGET_NUMBER_CB),
                InlineKeyboardButton(text="♾ Cheksiz", callback_data=TARGET_UNLIMITED_CB),
            ]
        ]
    )


def _projects_list_kb(projects: list[Project]) -> InlineKeyboardMarkup:
    rows = []
    for p in projects:
        mark = "🟢" if p.is_active else "⚪"
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{mark} {p.queue_order}. {p.name}",
                    callback_data=ProjectActionCB(project_id=p.id, action="view").pack(),
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="➕ Loyiha qo'shish", callback_data=ADD_PROJECT_CB)])
    return admin_kb.with_back_row(rows)


def _detail_text(project: Project) -> str:
    status = "🟢 Faol" if project.is_active else "⚪ Navbatda"
    target = str(project.target_votes) if project.target_votes is not None else "cheksiz"
    return (
        f"📁 <b>{project.name}</b>\n"
        f"🔗 {project.board_url}\n"
        f"Holat: {status}\n"
        f"Auto-stop: {project.confirmed_votes_count}/{target}\n"
    )


def _detail_kb(project: Project) -> InlineKeyboardMarkup:
    def cb(action: str) -> str:
        return ProjectActionCB(project_id=project.id, action=action).pack()

    rows = [
        [
            InlineKeyboardButton(text="✏️ Nomi", callback_data=cb("rename")),
            InlineKeyboardButton(text="🔗 Havola", callback_data=cb("set_url")),
        ],
        [InlineKeyboardButton(text="🎯 Auto-stop", callback_data=cb("set_target_menu"))],
        [
            InlineKeyboardButton(text="⬆️", callback_data=cb("move_up")),
            InlineKeyboardButton(text="⬇️", callback_data=cb("move_down")),
        ],
    ]
    if not project.is_active:
        rows.append([InlineKeyboardButton(text="✅ Faollashtirish", callback_data=cb("activate"))])
    rows.append([InlineKeyboardButton(text="🗑 O'chirish", callback_data=cb("delete"))])
    rows.append([InlineKeyboardButton(text="« Loyihalar ro'yxati", callback_data=cb("back"))])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _render_list_text(session: AsyncSession) -> tuple[str, InlineKeyboardMarkup]:
    projects = await project_repo.list_projects(session)
    if not projects:
        return "📁 Hozircha loyihalar yo'q.", _projects_list_kb(projects)
    return "📁 Loyihalar (batafsil ko'rish uchun bosing):", _projects_list_kb(projects)


@router.callback_query(AdminMenuCB.filter(F.section == "projects"))
async def list_projects(callback: CallbackQuery, session: AsyncSession) -> None:
    text, kb = await _render_list_text(session)
    await callback.message.edit_text(text, reply_markup=kb)


@router.callback_query(F.data == ADD_PROJECT_CB)
async def add_project_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ProjectCreateStates.waiting_name)
    await callback.message.edit_text("Loyiha nomini kiriting:", reply_markup=admin_kb.cancel_kb())


@router.message(ProjectCreateStates.waiting_name, F.text)
async def project_name_received(message: Message, state: FSMContext) -> None:
    await state.update_data(name=message.text.strip())
    await state.set_state(ProjectCreateStates.waiting_url)
    await message.answer(
        "Loyiha havolasini kiriting (openbudget.uz):", reply_markup=admin_kb.cancel_kb()
    )


@router.message(ProjectCreateStates.waiting_url, F.text)
async def project_url_received(message: Message, state: FSMContext) -> None:
    url = message.text.strip()
    if not _is_valid_board_url(url):
        await message.answer(BOARD_URL_HINT, reply_markup=admin_kb.cancel_kb())
        return

    await state.update_data(board_url=url)
    await state.set_state(ProjectCreateStates.waiting_target_choice)
    await message.answer(
        "Auto-stop uchun ovozlar sonini belgilaymizmi yoki cheksiz qilamizmi?",
        reply_markup=_target_choice_kb(),
    )


@router.callback_query(ProjectCreateStates.waiting_target_choice, F.data == TARGET_UNLIMITED_CB)
async def target_unlimited(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    await _finalize_project(callback, session, state, target_votes=None)


@router.callback_query(ProjectCreateStates.waiting_target_choice, F.data == TARGET_NUMBER_CB)
async def target_number_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ProjectCreateStates.waiting_target_number)
    await callback.message.edit_text(
        "Nechta tasdiqlangan ovozdan so'ng auto-stop bo'lsin? (son kiriting)",
        reply_markup=admin_kb.cancel_kb(),
    )


@router.message(ProjectCreateStates.waiting_target_number, F.text)
async def target_number_received(message: Message, session: AsyncSession, state: FSMContext) -> None:
    if not message.text.strip().isdigit() or int(message.text.strip()) <= 0:
        await message.answer("❗ Musbat son kiriting:", reply_markup=admin_kb.cancel_kb())
        return
    await _finalize_project(message, session, state, target_votes=int(message.text.strip()))


async def _finalize_project(
    target, session: AsyncSession, state: FSMContext, target_votes: int | None
) -> None:
    data = await state.get_data()
    project = await project_service.create_project(
        session, name=data["name"], board_url=data["board_url"], target_votes=target_votes
    )
    await state.clear()

    target_str = str(target_votes) if target_votes is not None else "cheksiz"
    active_str = "✅ Bu loyiha hozir faol." if project.is_active else "Navbatda kutmoqda."
    text = f"📁 Loyiha qo'shildi: <b>{project.name}</b>\nAuto-stop: {target_str}\n{active_str}"

    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, reply_markup=_detail_kb(project))
    else:
        await target.answer(text, reply_markup=_detail_kb(project))


# ---- detail view + edit actions ----


@router.callback_query(ProjectActionCB.filter(F.action == "view"))
async def project_view(
    callback: CallbackQuery, callback_data: ProjectActionCB, session: AsyncSession
) -> None:
    project = await project_repo.get_by_id(session, callback_data.project_id)
    if project is None:
        await callback.answer("Loyiha topilmadi.", show_alert=True)
        return
    await callback.message.edit_text(_detail_text(project), reply_markup=_detail_kb(project))


@router.callback_query(ProjectActionCB.filter(F.action == "back"))
async def project_back(callback: CallbackQuery, session: AsyncSession) -> None:
    text, kb = await _render_list_text(session)
    await callback.message.edit_text(text, reply_markup=kb)


@router.callback_query(ProjectActionCB.filter(F.action == "rename"))
async def project_rename_prompt(
    callback: CallbackQuery, callback_data: ProjectActionCB, state: FSMContext
) -> None:
    await state.set_state(ProjectEditStates.waiting_new_name)
    await state.update_data(project_id=callback_data.project_id)
    await callback.message.edit_text("Yangi nomni kiriting:", reply_markup=admin_kb.cancel_kb())


@router.message(ProjectEditStates.waiting_new_name, F.text)
async def project_rename_apply(message: Message, session: AsyncSession, state: FSMContext) -> None:
    data = await state.get_data()
    project = await project_repo.get_by_id(session, data["project_id"])
    if project is None:
        await state.clear()
        await message.answer("Loyiha topilmadi.", reply_markup=admin_kb.with_back_row([]))
        return
    await project_service.rename(session, project, message.text.strip())
    await state.clear()
    await message.answer(_detail_text(project), reply_markup=_detail_kb(project))


@router.callback_query(ProjectActionCB.filter(F.action == "set_url"))
async def project_set_url_prompt(
    callback: CallbackQuery, callback_data: ProjectActionCB, state: FSMContext
) -> None:
    await state.set_state(ProjectEditStates.waiting_new_url)
    await state.update_data(project_id=callback_data.project_id)
    await callback.message.edit_text(
        "Yangi havolani kiriting (openbudget.uz):", reply_markup=admin_kb.cancel_kb()
    )


@router.message(ProjectEditStates.waiting_new_url, F.text)
async def project_set_url_apply(message: Message, session: AsyncSession, state: FSMContext) -> None:
    url = message.text.strip()
    if not _is_valid_board_url(url):
        await message.answer(BOARD_URL_HINT, reply_markup=admin_kb.cancel_kb())
        return
    data = await state.get_data()
    project = await project_repo.get_by_id(session, data["project_id"])
    if project is None:
        await state.clear()
        await message.answer("Loyiha topilmadi.", reply_markup=admin_kb.with_back_row([]))
        return
    await project_service.set_board_url(session, project, url)
    await state.clear()
    await message.answer(_detail_text(project), reply_markup=_detail_kb(project))


@router.callback_query(ProjectActionCB.filter(F.action == "set_target_menu"))
async def project_target_menu(callback: CallbackQuery, callback_data: ProjectActionCB) -> None:
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔢 Son kiritish",
                    callback_data=ProjectActionCB(
                        project_id=callback_data.project_id, action="set_target_number"
                    ).pack(),
                ),
                InlineKeyboardButton(
                    text="♾ Cheksiz",
                    callback_data=ProjectActionCB(
                        project_id=callback_data.project_id, action="set_target_unlimited"
                    ).pack(),
                ),
            ]
        ]
    )
    await callback.message.edit_text("Auto-stop qiymatini tanlang:", reply_markup=kb)


@router.callback_query(ProjectActionCB.filter(F.action == "set_target_unlimited"))
async def project_target_unlimited(
    callback: CallbackQuery, callback_data: ProjectActionCB, session: AsyncSession
) -> None:
    project = await project_repo.get_by_id(session, callback_data.project_id)
    if project is None:
        await callback.answer("Loyiha topilmadi.", show_alert=True)
        return
    await project_service.set_target_votes(session, project, None)
    await callback.message.edit_text(_detail_text(project), reply_markup=_detail_kb(project))


@router.callback_query(ProjectActionCB.filter(F.action == "set_target_number"))
async def project_target_number_prompt(
    callback: CallbackQuery, callback_data: ProjectActionCB, state: FSMContext
) -> None:
    await state.set_state(ProjectEditStates.waiting_new_target_number)
    await state.update_data(project_id=callback_data.project_id)
    await callback.message.edit_text(
        "Nechta ovozdan so'ng auto-stop bo'lsin? (son kiriting)", reply_markup=admin_kb.cancel_kb()
    )


@router.message(ProjectEditStates.waiting_new_target_number, F.text)
async def project_target_number_apply(
    message: Message, session: AsyncSession, state: FSMContext
) -> None:
    if not message.text.strip().isdigit() or int(message.text.strip()) <= 0:
        await message.answer("❗ Musbat son kiriting:", reply_markup=admin_kb.cancel_kb())
        return
    data = await state.get_data()
    project = await project_repo.get_by_id(session, data["project_id"])
    if project is None:
        await state.clear()
        await message.answer("Loyiha topilmadi.", reply_markup=admin_kb.with_back_row([]))
        return
    await project_service.set_target_votes(session, project, int(message.text.strip()))
    await state.clear()
    await message.answer(_detail_text(project), reply_markup=_detail_kb(project))


@router.callback_query(ProjectActionCB.filter(F.action.in_({"move_up", "move_down"})))
async def project_move(
    callback: CallbackQuery, callback_data: ProjectActionCB, session: AsyncSession
) -> None:
    project = await project_repo.get_by_id(session, callback_data.project_id)
    if project is None:
        await callback.answer("Loyiha topilmadi.", show_alert=True)
        return
    direction = "up" if callback_data.action == "move_up" else "down"
    moved = await project_service.move(session, project, direction)
    if not moved:
        await callback.answer("Bu tomonda boshqa loyiha yo'q.", show_alert=True)
        return
    await callback.message.edit_text(_detail_text(project), reply_markup=_detail_kb(project))


@router.callback_query(ProjectActionCB.filter(F.action == "activate"))
async def project_activate(
    callback: CallbackQuery, callback_data: ProjectActionCB, session: AsyncSession
) -> None:
    project = await project_repo.get_by_id(session, callback_data.project_id)
    if project is None:
        await callback.answer("Loyiha topilmadi.", show_alert=True)
        return
    await project_service.switch_active(session, project)
    await callback.message.edit_text(_detail_text(project), reply_markup=_detail_kb(project))
    await callback.answer("Faollashtirildi.")


@router.callback_query(ProjectActionCB.filter(F.action == "delete"))
async def project_delete_confirm(callback: CallbackQuery, callback_data: ProjectActionCB) -> None:
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Ha, o'chirish",
                    callback_data=ProjectActionCB(
                        project_id=callback_data.project_id, action="delete_confirm"
                    ).pack(),
                ),
                InlineKeyboardButton(
                    text="« Yo'q",
                    callback_data=ProjectActionCB(
                        project_id=callback_data.project_id, action="view"
                    ).pack(),
                ),
            ]
        ]
    )
    await callback.message.edit_text("Rostdan ham o'chirmoqchimisiz?", reply_markup=kb)


@router.callback_query(ProjectActionCB.filter(F.action == "delete_confirm"))
async def project_delete_apply(
    callback: CallbackQuery, callback_data: ProjectActionCB, session: AsyncSession
) -> None:
    project = await project_repo.get_by_id(session, callback_data.project_id)
    if project is None:
        await callback.answer("Loyiha topilmadi.", show_alert=True)
        return
    await project_service.delete_project(session, project)
    text, kb = await _render_list_text(session)
    await callback.message.edit_text(f"🗑 Loyiha o'chirildi.\n\n{text}", reply_markup=kb)
