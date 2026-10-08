from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from onboarder.core.calls import resolve_calls
from onboarder.core.graph import DependencyGraph
from onboarder.core.models import Confidence
from onboarder.core.parser import parse_python_file
from onboarder.core.resolver import resolve_project
from onboarder.core.scanner import find_python_files


@dataclass(frozen=True)
class OnboardingGuide:
    root: Path
    entry_points: tuple[Path, ...]
    most_imported: tuple[tuple[Path, int], ...]
    reading_order: tuple[Path, ...]
    cycles: tuple[tuple[Path, ...], ...]
    folder_counts: tuple[tuple[str, int], ...]
    call_counts: dict[str, int]
    not_stored: dict[str, int]
    resolution_rate: float

    @property
    def not_stored_count(self) -> int:
        return sum(self.not_stored.values())

    def render(self) -> str:
        lines = ["Onboarding Guide", "", "Entry points:"]
        lines.extend(f"  {_relative(path, self.root)}" for path in self.entry_points)
        if not self.entry_points:
            lines.append("  (none)")

        lines.extend(("", "Most imported project files:"))
        lines.extend(
            f"  {_relative(path, self.root)} ({count} importing files)"
            for path, count in self.most_imported
        )
        if not self.most_imported:
            lines.append("  (none)")

        lines.extend(("", "Reading order:"))
        lines.extend(f"  {index}. {_relative(path, self.root)}" for index, path in enumerate(self.reading_order, 1))
        if not self.reading_order:
            lines.append("  (none)")

        lines.extend(("", "Cycles:"))
        lines.extend(
            "  " + " -> ".join(_relative(path, self.root) for path in cycle)
            for cycle in self.cycles
        )
        if not self.cycles:
            lines.append("  (none)")

        lines.extend(("", "Files by top-level folder:"))
        lines.extend(f"  {folder}: {count}" for folder, count in self.folder_counts)

        resolved = self.call_counts["exact"] + self.call_counts["inferred"]
        unresolved = self.call_counts["unresolved"]
        lines.extend(("", "Quality:", "  Call edges by confidence:"))
        lines.extend(f"    {name}: {self.call_counts[name]}" for name in ("exact", "inferred", "unresolved"))
        lines.append(f"  Stored unresolved calls: {unresolved}")
        lines.append(f"  Not-stored calls: {self.not_stored_count}")
        lines.extend(f"    {reason}: {count}" for reason, count in sorted(self.not_stored.items()))
        lines.append(
            f"  Resolution rate: {self.resolution_rate:.1%} ({resolved}/{resolved + unresolved})"
        )
        return "\n".join(lines)


def _relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def build_guide(root: Path) -> OnboardingGuide:
    root = Path(root).absolute()
    files = tuple(find_python_files(root))
    facts = {path: parse_python_file(path, project_root=root) for path in files}
    imports = resolve_project(root)
    calls = resolve_calls(root)

    entry_points = tuple(
        sorted(
            (
                path
                for path in files
                if facts[path].has_main_guard or path.name.lower() in {"main.py", "app.py", "manage.py"}
            ),
            key=lambda path: _relative(path, root),
        )
    )

    importers: dict[Path, set[Path]] = defaultdict(set)
    adjacency: dict[Path, set[Path]] = defaultdict(set)
    for edge in imports:
        if edge.confidence == Confidence.EXACT and edge.dst_file is not None:
            importers[edge.dst_file].add(edge.src_file)
            adjacency[edge.src_file].add(edge.dst_file)
    most_imported = tuple(
        sorted(
            ((path, len(sources)) for path, sources in importers.items()),
            key=lambda item: (-item[1], _relative(item[0], root)),
        )[:10]
    )

    score = {path: len(sources) for path, sources in importers.items()}
    ordered: list[Path] = list(entry_points)
    visited = set(ordered)
    frontier = list(entry_points)
    for _ in range(2):
        discovered = {
            dependency
            for source in frontier
            for dependency in adjacency.get(source, set())
            if dependency not in visited
        }
        next_frontier = sorted(
            discovered,
            key=lambda path: (-score.get(path, 0), _relative(path, root)),
        )
        ordered.extend(next_frontier)
        visited.update(next_frontier)
        frontier = next_frontier

    folder_counts_counter: Counter[str] = Counter()
    for path in files:
        relative = path.relative_to(root)
        folder_counts_counter[relative.parts[0] if len(relative.parts) > 1 else "(root)"] += 1
    folder_counts = tuple(sorted(folder_counts_counter.items()))

    cycles = DependencyGraph(imports, root=root).find_cycles()
    call_counts = {
        confidence.value: sum(edge.confidence == confidence for edge in calls.edges)
        for confidence in (Confidence.EXACT, Confidence.INFERRED, Confidence.UNRESOLVED)
    }
    resolved_count = call_counts[Confidence.EXACT.value] + call_counts[Confidence.INFERRED.value]
    unresolved_count = call_counts[Confidence.UNRESOLVED.value]
    denominator = resolved_count + unresolved_count
    resolution_rate = resolved_count / denominator if denominator else 0.0
    not_stored = {
        "unknown receiver": calls.stats.unknown_receiver,
        "external package": calls.stats.external_package,
        "builtin": calls.stats.builtin,
    }
    return OnboardingGuide(
        root,
        entry_points,
        most_imported,
        tuple(ordered),
        cycles,
        folder_counts,
        call_counts,
        not_stored,
        resolution_rate,
    )