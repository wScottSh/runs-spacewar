"""Names macro1 defines before reading a program, read from its source
(tools/macro1.c `pseudos` and `permanent_symbols`). macro1 compares symbols
on their first 6 characters. A generated label must not be one of these."""
from __future__ import annotations

import re
from pathlib import Path

MACRO1_SOURCE = Path(__file__).parent.parent / "macro1.c"
SYMBOL_LEN = 6
PSEUDO_PREFIX_LEN = 3


def _table(source: str, name: str) -> list[str]:
    """The symbol names of macro1's initializer `SYM_T name[] = { ... };`."""
    m = re.search(rf"SYM_T\s+{name}\[\]\s*=\s*\{{(.*?)\n\}};", source, re.S)
    if m is None:
        raise RuntimeError(f"{MACRO1_SOURCE}: no table {name}[]")
    return re.findall(r'\{\s*\w+\s*,\s*"([^"]+)"', m.group(1))


_SOURCE = MACRO1_SOURCE.read_text()
PSEUDOS = _table(_SOURCE, "pseudos")
PREDEFINED = frozenset(s[:SYMBOL_LEN] for s in PSEUDOS + _table(_SOURCE, "permanent_symbols"))

# macro1 reads a symbol it has not seen defined as any pseudo-op that shares
# its first three characters (`lookup`), so `\state` is `start`.
PSEUDO_PREFIXES = frozenset(p[:PSEUDO_PREFIX_LEN] for p in PSEUDOS)


def predefined(sym: str) -> bool:
    return sym[:SYMBOL_LEN] in PREDEFINED or sym[:PSEUDO_PREFIX_LEN] in PSEUDO_PREFIXES
