"""PC 与 Arduino 之间的简单文本协议。"""

from __future__ import annotations

import re


_DISTANCE_PATTERNS = (
    re.compile(
        r"(?:DIST(?:ANCE)?|RANGE|距离)\s*[:=：]?\s*"
        r"(-?\d+(?:\.\d+)?)\s*(mm|cm|m|毫米|厘米|米)?",
        re.IGNORECASE,
    ),
    re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*(mm|cm|m|毫米|厘米|米)?\s*$", re.IGNORECASE),
)


def parse_distance(message: str) -> tuple[float, str] | None:
    """从 Arduino 返回的一行文本中提取距离和单位。

    支持 ``DIST: 12.3 cm``、``Distance=120mm``、``距离: 1.2米``，
    也兼容只返回数字的程序。没有单位时默认使用 cm。
    """

    for pattern in _DISTANCE_PATTERNS:
        match = pattern.search(message.strip())
        if not match:
            continue
        value = float(match.group(1))
        raw_unit = (match.group(2) or "cm").lower()
        unit_map = {"毫米": "mm", "厘米": "cm", "米": "m"}
        return value, unit_map.get(raw_unit, raw_unit)
    return None


def make_command(command: str, value: str | None = None) -> bytes:
    """生成以换行结尾的 UTF-8 命令。"""

    command = command.strip().upper()
    text = f"{command}:{value.strip()}" if value is not None else command
    return (text + "\n").encode("utf-8")
