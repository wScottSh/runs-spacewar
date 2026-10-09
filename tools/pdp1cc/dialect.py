"""C AST -> IR. Resolves every name to a Storage from its declaration and
rejects anything outside the dialect with a message naming the construct."""
from __future__ import annotations

from pycparser import c_ast, c_generator

from . import ir

PAIR_OPS = {"rcl"}
BIN_OPS = {"+", "-", "&", "|", "^"}
CMP_OPS = {"<", ">=", "==", "!=", "<=", ">"}


class DialectError(Exception):
    pass


def _err(node: c_ast.Node, msg: str) -> DialectError:
    where = f"{node.coord}: " if node is not None and node.coord else ""
    return DialectError(where + msg)


def _attrs(decl: c_ast.Decl) -> set[str]:
    """Names of the pdp1_* attributes on a declaration, in any position."""
    gen = c_generator.CGenerator()
    found: set[str] = set()
    for spec in decl.funcspec or []:
        if hasattr(spec, "exprlist"):
            found.add(gen.visit(spec.exprlist))
    t = decl.type
    while t is not None:
        attrs = getattr(t, "attributes", None)
        if attrs is not None and attrs.exprs:
            found.add(gen.visit(attrs))
        t = getattr(t, "type", None)
    return {a for a in found if a}


def _is_function(t: c_ast.Node) -> bool:
    return isinstance(t, c_ast.FuncDecl) or type(t).__name__ == "FuncDeclExt"


def _base_type(t: c_ast.Node) -> str | None:
    if isinstance(t, c_ast.TypeDecl) and isinstance(t.type, c_ast.IdentifierType):
        return " ".join(t.type.names)
    return None


def c_int(node: c_ast.Node) -> int:
    """A compile-time C integer constant expression."""
    if isinstance(node, c_ast.Constant) and node.type == "int":
        text = node.value.rstrip("uUlL")
        return int(text, 8 if _is_octal(text) else 0)
    if isinstance(node, c_ast.UnaryOp) and node.op == "-":
        return -c_int(node.expr)
    raise _err(node, "expected a compile-time integer constant")


def _is_octal(text: str) -> bool:
    return len(text) > 1 and text[0] == "0" and text[1] not in "xXbB"


def to_word(value: int, node: c_ast.Node) -> int:
    """C integer -> 18-bit word. A negative constant is the ones' complement."""
    if abs(value) > ir.WORD_MASK:
        raise _err(node, f"constant {value:#o} does not fit an 18-bit word")
    return value if value >= 0 else (-value) ^ ir.WORD_MASK


class _Scope:
    def __init__(self, globals_: dict[str, ir.Storage]):
        self.frames: list[dict[str, ir.Storage]] = [globals_]

    def lookup(self, node: c_ast.ID) -> ir.Var:
        for frame in reversed(self.frames):
            if node.name in frame:
                return ir.Var(node.name, frame[node.name])
        raise _err(node, f"undeclared name {node.name!r}")


def lower_unit(ast: c_ast.FileAST) -> ir.Unit:
    globals_: dict[str, ir.Storage] = {}
    for ext in ast.ext:
        if isinstance(ext, c_ast.Decl) and not _is_function(ext.type):
            if ext.init is not None:
                globals_[ext.name] = ir.Placed(ext.name)
            elif "extern" in ext.storage:
                globals_.setdefault(ext.name, ir.Extern(ext.name))
            else:
                raise _err(ext, f"{ext.name}: uninitialized file-scope object "
                                "(pool variable) is not in the implemented dialect yet")

    items: list[ir.TopItem] = []
    for ext in ast.ext:
        if isinstance(ext, c_ast.FuncDef):
            items.append(_lower_function(ext, globals_))
        elif isinstance(ext, c_ast.Decl) and ext.init is not None:
            if _base_type(ext.type) != "word":
                raise _err(ext, f"{ext.name}: only `word` objects can be placed")
            items.append(ir.Datum(ext.name, to_word(c_int(ext.init), ext.init)))
    return ir.Unit(tuple(items))


def _lower_function(fn: c_ast.FuncDef, globals_: dict[str, ir.Storage]) -> ir.Function:
    decl = fn.decl
    attrs = _attrs(decl)
    if "pdp1_jda" not in attrs:
        raise _err(decl, f"{decl.name}: calling convention required "
                         "(only JDA is in the implemented dialect yet)")
    ftype = decl.type
    params = [p for p in (ftype.args.params if ftype.args else [])
              if not (isinstance(p, c_ast.Typename) and _base_type(p.type) == "void")]
    if len(params) > 1:
        raise _err(decl, f"{decl.name}: inline JDA parameters are not implemented yet")
    scope = _Scope(globals_)
    frame: dict[str, ir.Storage] = {}
    param = None
    if params:
        p = params[0]
        if _base_type(p.type) != "word":
            raise _err(p, "a JDA parameter must be a `word`")
        frame[p.name] = ir.Entry(decl.name)
        param = ir.Var(p.name, frame[p.name])
    scope.frames.append(frame)
    returns_value = _base_type(ftype.type) == "word"
    body = _Lowerer(scope).block(fn.body)
    return ir.Function(decl.name, "jda", param, body, returns_value)


class _Lowerer:
    def __init__(self, scope: _Scope):
        self.scope = scope

    # ---------------------------------------------------------- statements
    def block(self, node: c_ast.Compound) -> ir.Block:
        self.scope.frames.append({})
        out: list[ir.Stmt] = []
        for item in node.block_items or []:
            s = self.stmt(item)
            if s is not None:
                out.append(s)
        self.scope.frames.pop()
        return ir.Block(tuple(out))

    def stmt(self, node: c_ast.Node) -> ir.Stmt | None:
        match node:
            case c_ast.Compound():
                return self.block(node)
            case c_ast.Decl():
                return self.local(node)
            case c_ast.Assignment(op="="):
                target = self.lvalue(node.lvalue)
                return ir.Assign(target, self.expr(node.rvalue))
            case c_ast.UnaryOp(op="++") | c_ast.FuncCall():
                return ir.Eval(self.expr(node))
            case c_ast.If():
                return ir.If(self.cond(node.cond), self.stmt(node.iftrue),
                             self.stmt(node.iffalse) if node.iffalse else None)
            case c_ast.For(init=None, cond=None, next=None):
                return ir.Forever(self.stmt(node.stmt))
            case c_ast.Continue():
                return ir.Continue()
            case c_ast.Return():
                return ir.Return(self.expr(node.expr) if node.expr else None)
            case c_ast.EmptyStatement():
                return None
        raise _err(node, f"statement {type(node).__name__} is not in the implemented dialect yet")

    def local(self, node: c_ast.Decl) -> ir.Stmt | None:
        if _base_type(node.type) != "word":
            raise _err(node, f"{node.name}: locals must be `word`")
        if "static" in node.storage or "extern" in node.storage:
            raise _err(node, f"{node.name}: static locals are not implemented yet")
        storage = ir.Io(node.name) if "register" in node.storage else ir.Acc(node.name)
        self.scope.frames[-1][node.name] = storage
        if node.init is None:
            return None
        return ir.Assign(ir.Var(node.name, storage), self.expr(node.init))

    def lvalue(self, node: c_ast.Node) -> ir.Var:
        if not isinstance(node, c_ast.ID):
            raise _err(node, "only plain names can be assigned")
        return self.scope.lookup(node)

    def cond(self, node: c_ast.Node) -> ir.Compare:
        if isinstance(node, c_ast.BinaryOp) and node.op in CMP_OPS:
            if to_word(c_int(node.right), node.right) != 0:
                raise _err(node, "conditions compare with 0 only (the skip group)")
            return ir.Compare(node.op, self.expr(node.left))
        raise _err(node, "a condition must be `e <op> 0`")

    # --------------------------------------------------------- expressions
    def expr(self, node: c_ast.Node) -> ir.Expr:
        match node:
            case c_ast.Constant(type="int"):
                return ir.Const(to_word(c_int(node), node))
            case c_ast.ID():
                return self.scope.lookup(node)
            case c_ast.UnaryOp(op="-", expr=c_ast.Constant()):
                return ir.Const(to_word(c_int(node), node))
            case c_ast.UnaryOp(op="-" | "~"):
                return ir.Neg(self.expr(node.expr))
            case c_ast.UnaryOp(op="++"):
                return ir.PreInc(self.lvalue(node.expr))
            case c_ast.BinaryOp(op="<<" | ">>"):
                return ir.Shift(node.op, self.expr(node.left), c_int(node.right))
            case c_ast.BinaryOp() if node.op in BIN_OPS:
                return ir.Binary(node.op, self.expr(node.left), self.expr(node.right))
            case c_ast.FuncCall(name=c_ast.ID(name=name)) if name in PAIR_OPS:
                args = node.args.exprs if node.args else []
                if len(args) != 3:
                    raise _err(node, f"{name}(hi, lo, n) takes three arguments")
                return ir.PairOp(name, self.lvalue(args[0]), self.lvalue(args[1]), c_int(args[2]))
        raise _err(node, f"expression {type(node).__name__} is not in the implemented dialect yet")
