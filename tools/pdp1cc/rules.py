"""The rule registry. Every emitted Word names one of these ids."""

RULES: dict[str, str] = {
    "ST-PLACED": "initialized file-scope word: a data word at its definition",
    "JDA-ENTRY": "JDA function entry word; it is the first parameter's storage",
    "JDA-PROLOGUE": "JDA prologue: `dap R` patches the exit cell with the return address",
    "LAY-EXIT": "exit cell `R, jmp .`, owned by the source-last return",
    "RET": "`return` that is not the source-last one: `jmp R`",
    "EX-LOAD": "memory operand into AC: `lac x`",
    "EX-LOAD-IO": "memory operand into a register (IO) local: `lio x`",
    "EX-CONST-AC": "constant into AC: 0 -> cla, |c| <= 07777 -> law / law i, else lac (c",
    "EX-BIN": "l op r: l into AC, then add/sub/and/ior/xor r (constant r -> literal)",
    "EX-UNARY": "-x / ~x: x into AC, cma",
    "EX-SHIFT": "x << n / x >> n: sal / sar in 9s chunks",
    "EX-ROT": "pair op on AC:IO: one instruction per 9s chunk",
    "EX-STORE": "x = e: e into AC, dac x",
    "EX-STORE-ZERO": "x = 0 to memory: dzm x",
    "EX-INC": "++x as statement or value: idx x",
    "IF-SINGLE": "if (c) S with S one word: skip_when(!c); S",
    "IF-MULTI": "if (c) S otherwise: skip_when(c); jmp Lelse; S; Lelse:",
    "FOR-EVER": "for (;;) S: top: S; jmp top",
    "CONTINUE": "continue: jmp top",
}


def check(rule: str) -> str:
    if rule not in RULES:
        raise KeyError(f"unregistered rule id {rule!r}")
    return rule
