import ast
import builtins
from collections import Counter
from pathlib import Path

from onboarder.core.models import (
    CallResolution,
    CallStats,
    Confidence,
    Edge,
    EdgeKind,
    FileFacts,
    Symbol,
)
from onboarder.core.parser import parse_python_file
from onboarder.core.resolver import resolve_project
from onboarder.core.scanner import find_python_files


def _module_name(path: Path, root: Path) -> str:
    relative = path.relative_to(root).with_suffix("")
    parts = list(relative.parts)
    if parts[0] == "src":
        parts.pop(0)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _dotted(node: ast.expr) -> tuple[str, ...] | None:
    if isinstance(node, ast.Name):
        return (node.id,)
    if isinstance(node, ast.Attribute):
        prefix = _dotted(node.value)
        return (*prefix, node.attr) if prefix is not None else None
    return None


def _class_bases(
    path: Path,
    imports: dict[str, tuple[str, Path | None, bool]],
    classes_by_name: dict[tuple[Path, str], Symbol],
) -> dict[str, tuple[str, ...]]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, UnicodeError, SyntaxError):
        return {}

    bases: dict[str, tuple[str, ...]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        class_symbol = classes_by_name.get((path, node.name))
        if class_symbol is None:
            continue
        resolved: list[str] = []
        for base in node.bases:
            dotted = _dotted(base)
            if dotted is None:
                continue
            if len(dotted) == 1:
                binding = imports.get(dotted[0])
                if binding is not None and binding[0]:
                    resolved.append(binding[0])
                else:
                    local = classes_by_name.get((path, dotted[0]))
                    if local is not None:
                        resolved.append(local.qualified_name)
            elif dotted[0] in imports:
                binding = imports[dotted[0]]
                if binding[0]:
                    resolved.append(f"{binding[0]}.{'.'.join(dotted[1:])}")
        bases[class_symbol.qualified_name] = tuple(resolved)
    return bases


def _source_imports(
    path: Path,
    facts: FileFacts,
    import_edges: tuple[Edge, ...],
    symbol_index: dict[Path, tuple[Symbol, ...]],
    module_files: dict[str, Path],
) -> dict[str, tuple[str, Path | None, bool]]:
    bindings: dict[str, tuple[str, Path | None, bool]] = {}
    for ref in facts.imports:
        matching = [edge for edge in import_edges if edge.src_file == path and edge.line == ref.line]
        if not ref.names:
            imported_module = ref.module
            edge = next((item for item in matching if item.dst_file is not None), None)
            alias = ref.aliases[0] if ref.aliases else None
            binding_name = alias or imported_module.split(".")[0]
            if edge is not None:
                module_name = imported_module
                bindings[binding_name] = (module_name, edge.dst_file, False)
            elif any(item.confidence == Confidence.EXTERNAL for item in matching):
                bindings[binding_name] = ("", None, True)
            continue

        for index, imported_name in enumerate(ref.names):
            alias = ref.aliases[index] if index < len(ref.aliases) else None
            binding_name = alias or imported_name
            edge = next(
                (
                    item
                    for item in matching
                    if item.dst_name.rsplit(".", maxsplit=1)[-1] == imported_name
                ),
                None,
            )
            if edge is None:
                continue
            symbol = next(
                (
                    candidate
                    for candidate in symbol_index.get(edge.dst_file, ())
                    if candidate.name == imported_name
                    and candidate.kind in ("class", "function")
                ),
                None,
            ) if edge.dst_file is not None else None
            if symbol is not None:
                bindings[binding_name] = (symbol.qualified_name, edge.dst_file, False)
            elif edge.dst_file is not None:
                module_name = next(
                    (name for name, module_path in module_files.items() if module_path == edge.dst_file),
                    "",
                )
                bindings[binding_name] = (module_name, edge.dst_file, False)
            elif edge.confidence == Confidence.EXTERNAL:
                bindings[binding_name] = ("", None, True)
    return bindings


def _earlier_assignments(path: Path, call_line: int) -> dict[str, str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, UnicodeError, SyntaxError):
        return {}
    functions = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.lineno <= call_line <= (node.end_lineno or node.lineno)
    ]
    if not functions:
        return {}
    function = min(functions, key=lambda node: (node.end_lineno or node.lineno) - node.lineno)
    assignments: list[ast.Assign | ast.AnnAssign] = []

    class AssignmentVisitor(ast.NodeVisitor):
        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            if node is function:
                self.generic_visit(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            if node is function:
                self.generic_visit(node)

        def visit_Assign(self, node: ast.Assign) -> None:
            if node.lineno < call_line:
                assignments.append(node)
            self.generic_visit(node.value)

        def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
            if node.lineno < call_line:
                assignments.append(node)
            if node.value is not None:
                self.generic_visit(node.value)

    AssignmentVisitor().visit(function)
    result: dict[str, str] = {}
    for node in sorted(assignments, key=lambda item: item.lineno):
        if node.value is None:
            continue
        dotted = _dotted(node.value.func) if isinstance(node.value, ast.Call) else None
        if dotted is None or len(dotted) != 1:
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            if isinstance(target, ast.Name):
                result[target.id] = dotted[0]
    return result


def resolve_calls(root: Path) -> CallResolution:
    """Resolve statically recognizable calls without importing project code."""
    root = Path(root).absolute()
    files = tuple(find_python_files(root))
    import_edges = resolve_project(root)
    facts_by_file = {path: parse_python_file(path, project_root=root) for path in files}
    symbols_by_file = {path: facts.symbols for path, facts in facts_by_file.items()}
    all_symbols = tuple(symbol for symbols in symbols_by_file.values() for symbol in symbols)
    symbols_by_qname = {symbol.qualified_name: symbol for symbol in all_symbols}
    classes_by_name = {
        (symbol.file, symbol.name): symbol for symbol in all_symbols if symbol.kind == "class"
    }
    global_symbols: dict[tuple[Path, str], Symbol] = {
        (symbol.file, symbol.name): symbol
        for symbol in all_symbols
        if symbol.kind in ("class", "function")
    }
    module_files = {
        _module_name(path, root): path
        for path in files
    }
    bindings_by_file = {
        path: _source_imports(path, facts, import_edges, symbols_by_file, module_files)
        for path, facts in facts_by_file.items()
    }
    bases_by_file = {
        path: _class_bases(
            path,
            bindings_by_file[path],
            classes_by_name,
        )
        for path in files
    }
    builtin_names = set(dir(builtins))
    edges: list[Edge] = []
    not_stored: Counter[str] = Counter()

    for path in files:
        facts = facts_by_file[path]
        bindings = bindings_by_file[path]
        for call in facts.calls:
            parts = call.name
            target: Symbol | None = None
            confidence = Confidence.EXACT
            constructor = False
            not_stored_reason: str | None = None

            if len(parts) == 1:
                name = parts[0]
                binding = bindings.get(name)
                if binding is not None and binding[2]:
                    not_stored_reason = "external_package"
                elif binding is not None and binding[0] in symbols_by_qname:
                    target = symbols_by_qname[binding[0]]
                else:
                    target = global_symbols.get((path, name))
                if target is not None and target.kind == "class":
                    constructor = True
                elif target is None and name in builtin_names:
                    not_stored_reason = "builtin"
            elif parts[0] == "self" and call.enclosing_class is not None and len(parts) == 2:
                direct = symbols_by_qname.get(f"{call.enclosing_class}.{parts[1]}")
                if direct is not None and direct.kind == "method":
                    target = direct
                else:
                    target = _inherited_method(
                        call.enclosing_class,
                        parts[1],
                        bases_by_file[path],
                        symbols_by_qname,
                    )
                    if target is not None:
                        confidence = Confidence.INFERRED
                    else:
                        target_name = f"{call.enclosing_class}.{parts[1]}"
                        edges.append(
                            Edge(
                                EdgeKind.CALLS,
                                path,
                                None,
                                target_name,
                                Confidence.UNRESOLVED,
                                call.line,
                                src_symbol=call.enclosing_symbol,
                            )
                        )
                        continue
            elif len(parts) > 2 and parts[0] in bindings and bindings[parts[0]][2]:
                not_stored_reason = "external_package"
            elif len(parts) == 2:
                receiver, member = parts
                binding = bindings.get(receiver)
                if binding is not None and binding[2]:
                    not_stored_reason = "external_package"
                elif binding is not None and binding[1] is not None and binding[0] not in symbols_by_qname:
                    module_path = binding[1]
                    target = next(
                        (
                            symbol
                            for symbol in symbols_by_file.get(module_path, ())
                            if symbol.name == member and symbol.kind in ("class", "function")
                        ),
                        None,
                    )
                    if target is None:
                        target_name = f"{binding[0]}.{member}"
                        edges.append(
                            Edge(
                                EdgeKind.CALLS,
                                path,
                                None,
                                target_name,
                                Confidence.UNRESOLVED,
                                call.line,
                                src_symbol=call.enclosing_symbol,
                            )
                        )
                        continue
                else:
                    assignment_types = _earlier_assignments(path, call.line)
                    assigned_class = assignment_types.get(receiver)
                    class_binding = bindings.get(assigned_class or "")
                    class_target = (
                        symbols_by_qname.get(class_binding[0])
                        if class_binding is not None
                        else global_symbols.get((path, assigned_class))
                        if assigned_class is not None
                        else None
                    )
                    if class_target is not None and class_target.kind == "class":
                        target = symbols_by_qname.get(f"{class_target.qualified_name}.{member}")
                        if target is not None:
                            confidence = Confidence.INFERRED
                    if target is None:
                        not_stored_reason = "unknown_receiver"
            else:
                not_stored_reason = "unknown_receiver"

            if not_stored_reason is not None:
                not_stored[not_stored_reason] += 1
                continue

            if target is None:
                unresolved_name = parts[0]
                edges.append(
                    Edge(
                        EdgeKind.CALLS,
                        path,
                        None,
                        unresolved_name,
                        Confidence.UNRESOLVED,
                        call.line,
                        src_symbol=call.enclosing_symbol,
                    )
                )
                continue

            constructor = target.kind == "class"
            edges.append(
                Edge(
                    EdgeKind.CALLS,
                    path,
                    target.file,
                    target.qualified_name,
                    confidence,
                    call.line,
                    src_symbol=call.enclosing_symbol,
                    dst_symbol=target.qualified_name,
                    constructor=constructor,
                )
            )

    edges.sort(
        key=lambda edge: (
            edge.src_file.relative_to(root).as_posix(),
            edge.line,
            edge.dst_name,
            str(edge.confidence),
        )
    )
    return CallResolution(
        tuple(edges),
        CallStats(
            unknown_receiver=not_stored["unknown_receiver"],
            external_package=not_stored["external_package"],
            builtin=not_stored["builtin"],
        ),
    )


def _inherited_method(
    class_name: str,
    method_name: str,
    bases: dict[str, tuple[str, ...]],
    symbols: dict[str, Symbol],
) -> Symbol | None:
    visited = {class_name}
    frontier = [class_name]
    for _ in range(5):
        next_frontier = []
        for current in sorted(frontier):
            for base in bases.get(current, ()):
                if base in visited:
                    continue
                visited.add(base)
                method = symbols.get(f"{base}.{method_name}")
                if method is not None and method.kind == "method":
                    return method
                next_frontier.append(base)
        frontier = next_frontier
        if not frontier:
            break
    return None