from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Task, User
from app.schemas import TaskCreate, TaskRead, TaskUpdate

router = APIRouter(prefix="/tasks", tags=["Tasks"])
NOT_FOUND = {404: {"description": "Задача или владелец не найдены"}}


async def find_task(id: int, session: AsyncSession) -> Task:
    task = await session.get(Task, id)
    if task is None:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    return task


async def check_owner(owner_id: int, session: AsyncSession):
    if await session.get(User, owner_id) is None:
        raise HTTPException(status_code=404, detail="Владелец не найден")


@router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED, responses=NOT_FOUND)
async def create_task(payload: TaskCreate, session: AsyncSession = Depends(get_session)):
    await check_owner(payload.owner_id, session)
    task = Task(**payload.model_dump())
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return task


@router.get("", response_model=list[TaskRead])
async def list_tasks(
    done: bool | None = None,
    owner_id: int | None = Query(default=None, gt=0),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
):
    query = select(Task).order_by(Task.id)
    if done is not None:
        query = query.where(Task.done == done)
    if owner_id is not None:
        query = query.where(Task.owner_id == owner_id)
    return (await session.scalars(query.limit(limit).offset(offset))).all()


@router.get("/{id}", response_model=TaskRead, responses=NOT_FOUND)
async def get_task(id: int, session: AsyncSession = Depends(get_session)):
    return await find_task(id, session)


@router.patch("/{id}", response_model=TaskRead, responses=NOT_FOUND)
async def update_task(id: int, payload: TaskUpdate, session: AsyncSession = Depends(get_session)):
    task = await find_task(id, session)
    changes = payload.model_dump(exclude_unset=True)
    if "owner_id" in changes:
        await check_owner(changes["owner_id"], session)
    for field, value in changes.items():
        setattr(task, field, value)
    await session.commit()
    await session.refresh(task)
    return task


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT, responses=NOT_FOUND)
async def delete_task(id: int, session: AsyncSession = Depends(get_session)):
    task = await find_task(id, session)
    await session.delete(task)
    await session.commit()
    return Response(status_code=204)
