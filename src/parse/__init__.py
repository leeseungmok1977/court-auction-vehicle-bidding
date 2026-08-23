"""응답 파싱·필드 매핑 패키지."""

from .list_parser import (
    VehicleItem,
    parse_list_response,
    parse_row,
    FUEL_CODE,
)
from .detail_parser import DetailInfo, parse_detail

__all__ = [
    "VehicleItem", "parse_list_response", "parse_row", "FUEL_CODE",
    "DetailInfo", "parse_detail",
]
