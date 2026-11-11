"""The Graphviz DOT format: the subset multiply.dot uses (node defaults,
nodes, labeled edges, dashed guard edges).

  uv run -q python docs/prototypes/graph-format/dot/load.py [N]"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import graph  # noqa: E402

ID = r'("[^"]+"|\w+)'


def attrs(s: str | None) -> dict[str, str]:
    return {k: v.strip('"') for k, v in re.findall(r'(\w+)=("[^"]*"|\w+)', s or "")}


def load(path: Path) -> graph.Graph:
    g, shape = graph.Graph("", [], {}, []), None
    text = "\n".join(line.split("//")[0] for line in path.read_text().splitlines())
    for stmt in re.split(r"[;\n]", text):
        stmt = stmt.strip()
        if not stmt or stmt == "}":
            continue
        if m := re.fullmatch(r"digraph (\w+) \{", stmt):
            g.name = m[1]
        elif m := re.fullmatch(r"node \[(.*)\]", stmt):
            shape = attrs(m[1])["shape"]
        elif m := re.fullmatch(ID + r" -> " + ID + r"(?: \[(.*)\])?", stmt):
            a, b, at = m[1].strip('"'), m[2].strip('"'), attrs(m[3])
            if at.get("style") == "dashed":
                g.arcs.append(graph.Arc(a, b, None, True, at["label"]))
            elif a in g.transitions:
                g.arcs.append(graph.Arc(b, a, at["label"], False))
            else:
                g.arcs.append(graph.Arc(a, b, at["label"], True))
        elif m := re.fullmatch(ID + r"(?: \[(.*)\])?", stmt):
            if shape == "circle":
                g.places.append(m[1].strip('"'))
            else:
                g.transitions[m[1]] = attrs(m[2])["label"]
        else:
            raise SyntaxError(f"{path.name}: {stmt!r}")
    return g


if __name__ == "__main__":
    sys.exit(graph.verify(load(Path(__file__).with_name("multiply.dot")),
                          int(sys.argv[1]) if len(sys.argv) > 1 else 20000))
