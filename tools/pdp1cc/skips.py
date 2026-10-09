"""Condition -> skip encoding. skip_when(c) is the skip that skips exactly
when c holds. Pure table; negation takes the complementary row."""

# AC compared with 0. Values are Macro skip expressions macro1 evaluates.
AC_SKIP: dict[str, str] = {
    "<": "sma",
    ">=": "spa",
    "==": "sza",
    "!=": "sza i",
    "<=": "sma+sza-skip",
    ">": "sma+sza-skip i",
}

NEGATE: dict[str, str] = {
    "<": ">=", ">=": "<", "==": "!=", "!=": "==", "<=": ">", ">": "<=",
}


def ac_skip_when(op: str) -> str:
    return AC_SKIP[op]


# IO compared with 0: the skip group tests only IO's sign.
IO_SKIP: dict[str, str] = {
    "<": "spi i",
    ">=": "spi",
}


def io_skip_when(op: str) -> str | None:
    return IO_SKIP.get(op)


def isp_skip_when(op: str) -> str | None:
    """`++m >= 0` is `isp m`. `++m < 0` has no skip: callers use IF-MULTI."""
    return "isp" if op == ">=" else None
