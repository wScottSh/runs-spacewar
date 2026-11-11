"""The transition-block format: the places, then one block per transition
with its wires.

  uv run -q python docs/prototypes/graph-format/blocks/load.py [N]"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import graph  # noqa: E402


def load(path: Path) -> graph.Graph:
    g, t = graph.Graph("", [], {}, []), None
    for line in path.read_text().splitlines():
        line = line.split("#")[0].rstrip()
        if not line:
            continue
        if m := re.fullmatch(r"network (\w+)", line):
            g.name = m[1]
        elif m := re.fullmatch(r"  place (\S+)", line):
            g.places.append(m[1])
        elif m := re.fullmatch(r"  transition (\w+): (\w+)", line):
            t = m[1]; g.transitions[t] = m[2]
        elif m := re.fullmatch(r"    when (\S+) (.+)", line):
            g.arcs.append(graph.Arc(m[1], t, None, True, m[2]))
        elif m := re.fullmatch(r"    (\w+) (<-|->) (\S+)", line):
            g.arcs.append(graph.Arc(m[3], t, m[1], m[2] == "<-"))
        else:
            raise SyntaxError(f"{path.name}: {line!r}")
    return g


if __name__ == "__main__":
    sys.exit(graph.verify(load(Path(__file__).with_name("multiply.net")),
                          int(sys.argv[1]) if len(sys.argv) > 1 else 20000))
