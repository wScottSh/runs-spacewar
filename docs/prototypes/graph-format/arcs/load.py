"""The arc-list format: places, transitions, then one arc a line.

  uv run -q python docs/prototypes/graph-format/arcs/load.py [N]"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import graph  # noqa: E402


def load(path: Path) -> graph.Graph:
    g, section = graph.Graph("", [], {}, []), None
    for line in path.read_text().splitlines():
        line = line.split("#")[0].rstrip()
        if not line:
            continue
        if line.startswith("network "):
            g.name = line.split()[1]
        elif not line.startswith(" "):
            section = line
        elif section == "places":
            g.places.append(line.strip())
        elif section == "transitions":
            t, p = line.split(":")
            g.transitions[t.strip()] = p.strip()
        elif m := re.fullmatch(r"\s+(\S+) -> (\w+) when (.+)", line):
            g.arcs.append(graph.Arc(m[1], m[2], None, True, m[3]))
        elif m := re.fullmatch(r"\s+(\w+\.\w+) -> (\w+)\.(\w+)", line):
            a, b, io = m.groups()
            if a.split(".")[0] in g.transitions:
                g.arcs.append(graph.Arc(f"{b}.{io}", a.split(".")[0], a.split(".")[1], False))
            else:
                g.arcs.append(graph.Arc(a, b, io, True))
        else:
            raise SyntaxError(f"{path.name}: {line!r}")
    return g


if __name__ == "__main__":
    sys.exit(graph.verify(load(Path(__file__).with_name("multiply.net")),
                          int(sys.argv[1]) if len(sys.argv) > 1 else 20000))
