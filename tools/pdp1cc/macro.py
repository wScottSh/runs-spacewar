"""Names macro1 defines before reading a program: its pseudo-ops and its
permanent symbols (tools/macro1.c `pseudos` and `permanent_symbols`). macro1
compares symbols on their first 6 characters. A generated label must not
be one of these."""

PREDEFINED = frozenset({
    "1s", "2s", "3s", "4s", "5s", "6s", "7s", "8s", "9s", "add", "and", "cal", "cbs", "charac",
    "cks", "cla", "clc", "clf", "cli", "clo", "cma", "consta", "dac", "dap", "decima", "define",
    "dio", "dip", "dis", "div", "dpy", "dzm", "eem", "esm", "expung", "flexo", "hlt", "i",
    "idx", "ioh", "ior", "iot", "isp", "jda", "jmp", "jsp", "lac", "lap", "lat", "law", "lem",
    "lio", "lsm", "mul", "mus", "noinpu", "nop", "octal", "opr", "ppa", "ppb", "ral", "rar",
    "rcl", "rcr", "repeat", "ril", "rir", "rpa", "rpb", "rrb", "sad", "sal", "sar", "sas",
    "scl", "scr", "sil", "sir", "skip", "skp", "sma", "spa", "spi", "start", "stf", "sub",
    "sza", "szf", "szo", "szs", "text", "tyi", "tyo", "variab", "xct", "xor", "xx"
})


# macro1 reads a symbol it has not seen defined as any pseudo-op that shares
# its first three characters (`lookup`), so `\state` is `start`.
PSEUDO_PREFIXES = frozenset(p[:3] for p in ("consta", "define", "repeat", "start", "variab", "text",
                                            "noinpu", "expung", "charac", "decima", "flexo", "octal"))


def predefined(sym: str) -> bool:
    return sym[:6] in PREDEFINED or sym[:3] in PSEUDO_PREFIXES
