from db.models.project import Project
from sqlalchemy.ext.asyncio import AsyncSession

from repositories import project_repo


async def create_project(
    session: AsyncSession,
    name: str,
    board_url: str,
    target_votes: int | None,
) -> Project:
    queue_order = await project_repo.get_next_queue_order(session)
    project = Project(
        name=name,
        board_url=board_url,
        queue_order=queue_order,
        target_votes=target_votes,
    )
    session.add(project)
    await session.flush()

    active = await project_repo.get_active_project(session)
    if active is None:
        project.is_active = True
        await session.flush()

    return project


async def advance_to_next(session: AsyncSession, current: Project) -> Project | None:
    """Deactivate `current` and activate the next eligible project by queue order.

    Used both by the auto-stop trigger (voting_service) and by a manual admin switch.
    """
    current.is_active = False
    await session.flush()

    next_project = await project_repo.get_next_in_queue(session, exclude_project_id=current.id)
    if next_project is not None:
        next_project.is_active = True
        await session.flush()
    return next_project


async def switch_active(session: AsyncSession, target: Project) -> None:
    """Manual admin switch: deactivate whatever is active, activate `target` directly."""
    current = await project_repo.get_active_project(session)
    if current is not None and current.id != target.id:
        current.is_active = False
    target.is_active = True
    await session.flush()


async def rename(session: AsyncSession, project: Project, new_name: str) -> None:
    project.name = new_name
    await session.flush()


async def set_board_url(session: AsyncSession, project: Project, new_url: str) -> None:
    project.board_url = new_url
    await session.flush()


async def set_bot_url(session: AsyncSession, project: Project, new_url: str | None) -> None:
    project.bot_url = new_url
    await session.flush()


async def set_target_votes(session: AsyncSession, project: Project, target_votes: int | None) -> None:
    project.target_votes = target_votes
    await session.flush()


async def move(session: AsyncSession, project: Project, direction: str) -> bool:
    """Swap `project`'s queue position with its neighbor. Returns False if there's no neighbor."""
    neighbor = await project_repo.get_neighbor(session, project, direction)
    if neighbor is None:
        return False
    project.queue_order, neighbor.queue_order = neighbor.queue_order, project.queue_order
    await session.flush()
    return True


async def delete_project(session: AsyncSession, project: Project) -> Project | None:
    """Soft-delete. If it was active, auto-advance to the next eligible project."""
    was_active = project.is_active
    project.is_deleted = True
    project.is_active = False
    await session.flush()

    if not was_active:
        return None

    next_project = await project_repo.get_next_in_queue(session, exclude_project_id=project.id)
    if next_project is not None:
        next_project.is_active = True
        await session.flush()
    return next_project
