from pydantic import BaseModel
from enum import Enum


class SourceEnum(Enum):
    ESHOP = "Электронный магазин"
    AISGZ = "АИС ГЗ"


class GetSuppliersRequest(BaseModel):
    okpd: str
    budget: int | None
    is_smp: bool = False
    source: SourceEnum = SourceEnum.AISGZ
    page: int = 1


class FindOKPDRequest(BaseModel):
    _str: str | None
