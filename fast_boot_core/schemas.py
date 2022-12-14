from datetime import date
from enum import Enum
from typing import Any, Generic, List, TypeVar, Union, Mapping

import orjson
from fastapi import Query
from pydantic import BaseModel, Field, validator
from pydantic.fields import ModelField
from pydantic.generics import GenericModel
from pydantic.json import timedelta_isoformat
from pydantic.schema import datetime, timedelta


def orjson_dumps(v, *, default):
    return orjson.dumps(v, default=default).decode()


TypeX = TypeVar("TypeX")


class Schema(BaseModel):
    class Config:
        json_loads = orjson.loads
        json_dumps = orjson_dumps
        json_encoders = {
            datetime: lambda v: v.timestamp(),
            date: lambda v: datetime(v.year, v.month, v.day).timestamp(),
            timedelta: timedelta_isoformat
        }
        orm_mode = True

    @validator('*', pre=True)
    def datetime_or_date_to_timestamp(cls, v, **kwargs):
        val: ModelField = kwargs['field']

        if val.type_ is datetime:
            try:
                bool(float(v))
                is_numeric = True
            except ValueError:
                is_numeric = False

            if v is None:
                return
            elif type(v) is datetime:
                return v.replace(tzinfo=None)
            elif type(v) in {int, float} or is_numeric:
                try:
                    return datetime.fromtimestamp(float(v))
                except Exception:
                    raise ValueError(f'{v} is not valid')
            elif type(v) is str:
                try:
                    return datetime.fromisoformat(v).timestamp()
                except Exception:
                    raise ValueError(f'{v} is not valid')
        if val.type_ is date:
            try:
                bool(float(v))
                is_numeric = True
            except ValueError:
                is_numeric = False

            if v is None:
                return
            elif type(v) is date:
                return v
            elif type(v) in {int, float} or is_numeric:
                try:
                    return datetime.fromtimestamp(float(v))
                except Exception:
                    raise ValueError(f'{v} is not valid')
            elif type(v) is str:
                try:
                    return datetime.strptime(v, '%Y-%m-%d').timestamp()
                except Exception:
                    raise ValueError(f'{v} is not valid')
        return v


class GenericSchema(Schema, GenericModel):
    ...


class Warn(BaseModel):
    loc: List[Union[str, int]] = []
    code: str = None
    msg: str = None


class PageResponse(GenericSchema, Generic[TypeX]):
    data: List[TypeX]
    total_items: int = 0
    total_page: int = 0
    current_page: int = 0
    warning: List[Warn] = []


class DataResponse(GenericSchema, Generic[TypeX]):
    data: TypeX = None
    warning: List[Warn] = []

    def __init__(self, data: TypeX, **kwargs: Any):
        kwargs.update(data=data)
        super().__init__(**kwargs)


# PAGING
class Sort(BaseModel):
    class Direction(str, Enum):
        ASC = "asc"
        DESC = "desc"

    order_by: str = None
    direction: Direction = None

    @classmethod
    def from_str(cls, sort_criteria: str):
        order_by = sort_criteria[:sort_criteria.index("(")]
        direction = sort_criteria[sort_criteria.index("(") + 1:sort_criteria.index(")")]
        return cls(order_by=order_by, direction=direction)

    def to_str(self):
        return f"{self.order_by}({self.direction})"

    @staticmethod
    def query_regex():
        return r"^.+\((?:{})\)$".format("|".join([v.value for v in Sort.Direction]))


class Pageable(BaseModel):
    sort: List[Sort] = Field([])
    size: int = Field(100, gt=0)
    page: int = Field(1, gt=0)

    def __init__(self, size: int, page: int, sort: List[Sort]):  # direction: Sort.Direction = Sort.Direction.DESC, order_by=None):
        super().__init__()
        self.sort = sort
        self.size = size
        self.page = page

    @classmethod
    def non_sort(cls, page: int = Query(1, ge=1), size: int = Query(100, ge=1)):
        return cls(size, page, [])

    @classmethod
    def standard(
            cls,
            page: int = Query(1, ge=1, description="Page number (1..N)"),
            size: int = Query(100, ge=1, description="The size of page to be returned"),
            sort: List[str] = Query([f"id({Sort.Direction.DESC})"], description="Sorting criteria in the format: property(asc|desc). Default sort order is descending.", regex=Sort.query_regex())
    ):
        return cls(size, page, list(map(Sort.from_str, sort)))

    @classmethod
    def with_default_attribute(cls, sorts: List[Sort]):
        def new_standard(
                page: int = Query(1, ge=1, description="Page number (1..N)"),
                size: int = Query(100, ge=1, description="The size of page to be returned"),
                sort: List[str] = Query(list(map(Sort.to_str, sorts)), description="Sorting criteria in the format: property(asc|desc). Default sort order is descending.", regex=Sort.query_regex())
        ):
            return Pageable(size, page, list(map(Sort.from_str, sort)))

        return new_standard

    @classmethod
    def old_standard(
            cls,
            page: int = Query(1, ge=1, description="Page number (1..N)"),
            limit: int = Query(20, ge=1, description="The size of page to be returned"),
            sort: List[str] = Query([f"id({Sort.Direction.DESC})"], description="Sorting criteria in the format: property(asc|desc). Default sort order is descending.", regex=Sort.query_regex())
    ):
        return cls(limit, page, list(map(Sort.from_str, sort)))

    def to_api_query(self) -> str:
        string = ""
        for key, value in self.dict().items():
            if isinstance(value, list):
                string += "".join([f"{key}={v['order_by']}({v['direction']})&" for v in value])
            else:
                string += f"{key}={value}&"
        return string[:-1]

    def to_api_mapping_query(self) -> Mapping[str, str]:
        return self.dict().items()
