from pathlib import Path

from onboarder.graph import build_graph

PROJECT = Path(__file__).parent / "fixtures" / "graph_project"


def test_dependencies_and_dependents() -> None:
    graph = build_graph(PROJECT)
    main = PROJECT / "main.py"
    alpha = PROJECT / "pkg" / "alpha.py"
    base = PROJECT / "chain" / "base.py"
    middle = PROJECT / "chain" / "middle.py"

    assert PROJECT / "pkg" / "core.py" in graph.dependencies(main)
    assert PROJECT / "pkg" / "submodule.py" in graph.dependencies(main)
    assert alpha in graph.dependents(PROJECT / "pkg" / "beta.py")
    assert graph.dependents(base) == (middle,)


def test_transitive_dependents_respect_depth_limit() -> None:
    graph = build_graph(PROJECT)
    base = PROJECT / "chain" / "base.py"
    middle = PROJECT / "chain" / "middle.py"
    top = PROJECT / "chain" / "top.py"

    assert graph.transitive_dependents(base, max_depth=1) == (middle,)
    assert graph.transitive_dependents(base, max_depth=2) == (middle, top)


def test_find_cycles_reports_multi_file_and_self_cycles() -> None:
    graph = build_graph(PROJECT)
    alpha = PROJECT / "pkg" / "alpha.py"
    beta = PROJECT / "pkg" / "beta.py"
    self_cycle = PROJECT / "pkg" / "self_cycle.py"

    assert (alpha, beta) in graph.find_cycles()
    assert (self_cycle,) in graph.find_cycles()


def test_non_circular_project_has_no_cycles(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "base.py").write_text("VALUE = 1\n", encoding="utf-8")
    (package / "consumer.py").write_text("from . import base\n", encoding="utf-8")

    assert build_graph(tmp_path).find_cycles() == ()