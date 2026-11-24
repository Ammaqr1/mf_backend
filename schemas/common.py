import math
from typing import Generic, TypeVar

from fastapi import Query
from pydantic import BaseModel

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    page: int
    per_page: int
    total: int
    total_pages: int


class PageParams:
    """Query params shared by every paginated list endpoint."""

    def __init__(
        self,
        page: int = Query(1, ge=1),
        per_page: int = Query(10, ge=1, le=100),
    ):
        self.page = page
        self.per_page = per_page

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.per_page


def make_page(items: list, params: PageParams, total: int) -> dict:
    return {
        "items": items,
        "page": params.page,
        "per_page": params.per_page,
        "total": total,
        "total_pages": max(1, math.ceil(total / params.per_page)),
    }
