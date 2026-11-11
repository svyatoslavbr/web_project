from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, model_validator


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: int
    email: EmailStr

    model_config = {"from_attributes": True}


class LinearSystemIn(BaseModel):
    matrix: list[list[float]]
    vector: list[float]

    @model_validator(mode="after")
    def check_shape(self):
        n = len(self.matrix)
        if n == 0 or any(len(row) != n for row in self.matrix):
            raise ValueError("Matrix must be square and non-empty")
        if len(self.vector) != n:
            raise ValueError("Vector length must match matrix size")
        return self


class GeneratedIn(BaseModel):
    n: int = Field(ge=2)
    seed: int = 0


class TaskCreate(BaseModel):
    kind: Literal["linear_system", "linear_generated"]
    data: LinearSystemIn | GeneratedIn


class TaskOut(BaseModel):
    id: int
    kind: str
    status: str
    progress: int
    stage: str
    result: dict | None
    error: str | None
    worker_host: str | None
    queue_position: int | None = None
    eta_seconds: float | None = None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    model_config = {"from_attributes": True}
