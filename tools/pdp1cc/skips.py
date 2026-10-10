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


def flag_skip_when(n: int, negated: bool) -> str:
    """`szf n` skips when program flag n is clear: skip_when(!flag(n))."""
    return f"szf {n}" if negated else f"szf i {n}"


def isp_skip_when(op: str) -> str | None:
    """`++m >= 0` is `isp m`. `++m < 0` has no skip: callers use IF-MULTI."""
    return "isp" if op == ">=" else None


def sense_skip_when(n: int, negated: bool) -> str:
    """`szs n0` skips when sense switch n is off: skip_when(!sense(n))."""
    return f"szs {n << 3:o}" if negated else f"szs i {n << 3:o}"


# AC compared with a memory word or a literal: sas skips when they are the
# same, sad when they differ.
SAME_SKIP: dict[str, str] = {"==": "sas", "!=": "sad"}


def same_skip_when(op: str) -> str:
    return SAME_SKIP[op]
