from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import User
from app.schemas import UserCreate, UserRead

router = APIRouter(prefix="/users", tags=["Users"])


@router.post(
    "",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    responses={409: {"description": "Email занят"}},
)
async def create_user(payload: UserCreate, session: AsyncSession = Depends(get_session)):
    user = User(**payload.model_dump())
    session.add(user)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        if getattr(exc.orig, "sqlstate", None) == "23505":
            raise HTTPException(status_code=409, detail="Email уже зарегистрирован") from exc
        raise
    await session.refresh(user)
    return user


@router.get(
    "/{id}", response_model=UserRead, responses={404: {"description": "Пользователь не найден"}}
)
async def get_user(id: int, session: AsyncSession = Depends(get_session)):
    user = await session.get(User, id)
    if user is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return user
