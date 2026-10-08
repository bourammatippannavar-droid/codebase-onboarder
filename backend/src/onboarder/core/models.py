from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Literal

SymbolKind = Literal["class", "function", "method"]
ExternalOrigin = Literal["stdlib", "third-party"]


class EdgeKind(StrEnum):
    IMPORTS = "imports"
    CALLS = "calls"


class Confidence(StrEnum):
    EXACT = "exact"
    INFERRED = "inferred"
    EXTERNAL = "external"
    UNRESOLVED = "unresolved"


IMPORTS = EdgeKind.IMPORTS


@dataclass(frozen=True)
class Symbol:
    kind: SymbolKind
    name: str
    qualified_name: str
    file: Path
    start_line: int
    end_line: int


@dataclass(frozen=True, eq=False)
class ImportRef:
    module: str
    names: tuple[str, ...]
    level: int
    line: int
    aliases: tuple[str | None, ...] = ()

    def render(self) -> str:
        if not self.names:
            alias = self.aliases[0] if self.aliases else None
            suffix = f" as {alias}" if alias else ""
            return f"import {self.module}{suffix}"

        aliases = self.aliases or (None,) * len(self.names)
        imported = ", ".join(
            name + (f" as {alias}" if alias else "")
            for name, alias in zip(self.names, aliases, strict=True)
        )
        return f"from {'.' * self.level}{self.module} import {imported}"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, ImportRef):
            return (
                self.module,
                self.names,
                self.level,
                self.line,
                self.aliases,
            ) == (
                other.module,
                other.names,
                other.level,
                other.line,
                other.aliases,
            )
        if isinstance(other, str):
            return self.render() == other
        return False


@dataclass(frozen=True)
class CallSite:
    name: tuple[str, ...]
    enclosing_symbol: str | None
    line: int
    enclosing_class: str | None = None


@dataclass(frozen=True)
class FileFacts:
    symbols: tuple[Symbol, ...]
    imports: tuple[ImportRef, ...]
    diagnostics: tuple[str, ...]
    has_main_guard: bool
    calls: tuple[CallSite, ...] = ()

    @property
    def classes(self) -> tuple[str, ...]:
        return tuple(symbol.name for symbol in self.symbols if symbol.kind == "class")

    @property
    def functions(self) -> tuple[str, ...]:
        functions = [symbol for symbol in self.symbols if symbol.kind in ("function", "method")]
        functions.sort(key=lambda symbol: (symbol.kind == "method", symbol.start_line))
        return tuple(symbol.name for symbol in functions)

    @property
    def error(self) -> str | None:
        return self.diagnostics[0] if self.diagnostics else None


@dataclass(frozen=True)
class Edge:
    kind: EdgeKind
    src_file: Path
    dst_file: Path | None
    dst_name: str
    confidence: Confidence
    line: int
    origin: ExternalOrigin | None = None
    src_symbol: str | None = None
    dst_symbol: str | None = None
    constructor: bool = False


@dataclass(frozen=True)
class CallStats:
    unknown_receiver: int = 0
    external_package: int = 0
    builtin: int = 0

    @property
    def not_stored_count(self) -> int:
        return self.unknown_receiver + self.external_package + self.builtin


@dataclass(frozen=True)
class CallResolution:
    edges: tuple[Edge, ...]
    stats: CallStats