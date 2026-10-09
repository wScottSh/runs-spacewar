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
    "GOTO": "goto L: jmp L; a C label names the first word of its statement",
    "EX-STEP": "mus(h, l, m) / dis(h, l, m): one multiply or divide step on AC:IO",
    "EX-MOVE": "value between AC and IO (register local from AC, or into AC): rcr 9s; rcr 9s",
    "EX-CONST-IO": "register local = 0: cli",
    "EX-STORE-IO": "x = register local: dio x",
    "JDA-CALL": "f(...) for a JDA f: AC argument, jda f",
    "JDA-BYNAME-ARG": "BYNAME argument: the inline word `lac x` (constant -> literal) after the call",
    "BYNAME-READ": "read of a BYNAME parameter: the cell R itself (`R, xct`) first, then `xct R`",
    "RET-INDIRECT": "return from a function with inline parameters: jmp i R",
    "ARGS": "skip the inline parameters: idx R, placed where AC is dead after the last read",
    "SKIP-RETURN": "skip_return(): idx R, the call returns one word further",
    "TAIL-CALL": "return blk(...) for a BLOCK blk: arguments, jmp blk",
    "LAY-FALLTHROUGH": "a tail call of the BLOCK laid out next emits no jump; tags that block's first word",
    "LAY-ADOPT": "a function whose returns all tail-call one BLOCK patches that block's exit",
    "LOOP-UNROLL": "for (int i = 0; i < N; i++) S: S emitted N times (N read as C reads it)",
    "ST-ENTRY-CELL": "ENTRY_CELL(f) object: f's entry word under another name",
    "SKIP-IO": "a register (IO) local compared with 0: io < 0 skips on `spi i`, io >= 0 on `spi`",
}


def check(rule: str) -> str:
    if rule not in RULES:
        raise KeyError(f"unregistered rule id {rule!r}")
    return rule
