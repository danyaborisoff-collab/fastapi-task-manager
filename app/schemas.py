from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class UserCreate(BaseModel):
    email: EmailStr = Field(max_length=320)
    name: str = Field(min_length=1, max_length=200)


class UserRead(UserCreate):
    id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class UserUpdate(BaseModel):
    email: EmailStr | None = Field(default=None, max_length=320)
    name: str | None = Field(default=None, min_length=1, max_length=200)

    @field_validator("email", "name")
    @classmethod
    def reject_null(cls, value):
        if value is None:
            raise ValueError("Поле не может быть null")
        return value


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    done: bool = False
    owner_id: int = Field(gt=0)


class TaskRead(TaskCreate):
    id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    done: bool | None = None
    owner_id: int | None = Field(default=None, gt=0)

    @field_validator("title", "done", "owner_id")
    @classmethod
    def reject_null(cls, value):
        if value is None:
            raise ValueError("Поле не может быть null")
        return value
