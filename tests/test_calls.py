from pathlib import Path

from onboarder.calls import resolve_calls
from onboarder.graph import build_graph
from onboarder.models import Confidence, EdgeKind
from onboarder.parser import parse_python_file

PROJECT = Path(__file__).parent / "fixtures" / "call_project"


def _edges_for(resolution, dst_name: str):
    return [edge for edge in resolution.edges if edge.dst_name.endswith(dst_name)]


def test_parser_extracts_dotted_call_sites_and_skips_dynamic_callees() -> None:
    facts = parse_python_file(PROJECT / "main.py", project_root=PROJECT)
    calls = facts.calls

    assert any(call.name == ("helper_module", "clean") for call in calls)
    assert any(call.name == ("repository", "save") for call in calls)
    assert any(call.name == ("factory",) for call in calls)
    assert not any(call.name == ("values",) for call in calls)
    assert all(
        call.enclosing_symbol == "main.py::main"
        for call in calls
        if call.line < 20
    )
    assert any(call.name == ("main",) and call.enclosing_symbol is None for call in calls)


def test_exact_calls_cover_local_import_alias_module_alias_and_constructor() -> None:
    resolution = resolve_calls(PROJECT)
    calls = [edge for edge in resolution.edges if edge.kind == EdgeKind.CALLS]

    assert any(
        edge.dst_symbol == "helpers.py::clean"
        and edge.confidence == Confidence.EXACT
        and edge.line == 9
        for edge in calls
    )
    assert any(
        edge.dst_symbol == "workers.py::local_target"
        and edge.confidence == Confidence.EXACT
        for edge in calls
    )
    assert any(
        edge.dst_symbol == "workers.py::Repository.validate"
        and edge.confidence == Confidence.EXACT
        for edge in calls
    )
    assert any(
        edge.dst_symbol == "workers.py::Repository"
        and edge.constructor
        and edge.confidence == Confidence.EXACT
        for edge in calls
    )
    assert any(
        edge.dst_symbol == "workers.py::Repository"
        and edge.constructor
        and edge.src_file.name == "main.py"
        for edge in calls
    )
    assert any(edge.dst_symbol == "helpers.py::clean" for edge in calls)


def test_inferred_calls_cover_base_methods_and_assigned_instances() -> None:
    resolution = resolve_calls(PROJECT)

    assert any(
        edge.dst_symbol == "workers.py::Base.inherited"
        and edge.confidence == Confidence.INFERRED
        for edge in resolution.edges
    )
    assert any(
        edge.dst_symbol == "workers.py::Repository.save"
        and edge.confidence == Confidence.INFERRED
        for edge in resolution.edges
    )


def test_unresolved_bare_and_self_calls_are_stored() -> None:
    resolution = resolve_calls(PROJECT)
    unresolved = [edge for edge in resolution.edges if edge.confidence == Confidence.UNRESOLVED]

    assert any(edge.dst_name == "missing_target" for edge in unresolved)
    assert any(edge.dst_name == "workers.py::CycleA.absent_from_cycle" for edge in unresolved)


def test_unknown_receivers_external_calls_and_builtins_are_counted_not_stored() -> None:
    resolution = resolve_calls(PROJECT)
    destinations = {edge.dst_name for edge in resolution.edges}

    assert not any(name.endswith(".save") and "obj" in name for name in destinations)
    assert "requests.get" not in destinations
    assert "len" not in destinations
    assert resolution.stats.unknown_receiver == 2
    assert resolution.stats.external_package == 1
    assert resolution.stats.builtin == 1


def test_cyclic_inheritance_is_bounded() -> None:
    resolution = resolve_calls(PROJECT)

    assert any(
        edge.confidence == Confidence.UNRESOLVED
        and edge.dst_name == "workers.py::CycleA.absent_from_cycle"
        for edge in resolution.edges
    )


def test_inheritance_resolution_stops_after_five_base_hops() -> None:
    resolution = resolve_calls(PROJECT)

    assert any(
        edge.confidence == Confidence.UNRESOLVED
        and edge.dst_name == "workers.py::Level6.deep_method"
        for edge in resolution.edges
    )


def test_instance_inference_uses_only_assignments_in_same_function() -> None:
    resolution = resolve_calls(PROJECT)

    assert not any(
        edge.src_symbol == "main.py::untyped_repository"
        and edge.dst_name.endswith("repository.save")
        for edge in resolution.edges
    )
    assert resolution.stats.unknown_receiver == 2


def test_graph_callers_callees_and_usages_include_import_bindings() -> None:
    graph = build_graph(PROJECT)
    target = "helpers.py::clean"

    assert graph.callers(target)
    assert graph.callees("main.py::main")
    usages = graph.usages(target)
    assert any(edge.kind == EdgeKind.CALLS for edge in usages)
    assert any(edge.kind == EdgeKind.IMPORTS for edge in usages)
    assert all(edge.confidence is not None for edge in usages)


def test_cli_ambiguous_plain_symbol_reports_candidates() -> None:
    from typer.testing import CliRunner

    from onboarder.cli import app

    result = CliRunner().invoke(app, ["callers", str(PROJECT), "run"])

    assert result.exit_code != 0
    assert "workers.py::Repository.run" in result.output
    assert "workers.py::Child.run" in result.output


def test_cli_qualified_symbol_queries_and_usages_show_edge_kinds() -> None:
    from typer.testing import CliRunner

    from onboarder.cli import app

    callers = CliRunner().invoke(
        app, ["callers", str(PROJECT), "helpers.py::clean"]
    )
    callees = CliRunner().invoke(
        app, ["callees", str(PROJECT), "workers.py::Repository.run"]
    )
    constructors = CliRunner().invoke(
        app, ["callees", str(PROJECT), "main.py::main"]
    )
    usages = CliRunner().invoke(
        app, ["usages", str(PROJECT), "helpers.py::clean"]
    )

    assert callers.exit_code == callees.exit_code == constructors.exit_code == usages.exit_code == 0
    assert "[exact]" in callers.output
    assert "CALLS" in callees.output
    assert "(constructor)" in constructors.output
    assert "CALLS" in usages.output
    assert "IMPORTS" in usages.output


def test_cli_find_searches_file_and_symbol_names_case_insensitively() -> None:
    from typer.testing import CliRunner

    from onboarder.cli import app

    result = CliRunner().invoke(app, ["find", str(PROJECT), "REPOSITORY"])

    assert result.exit_code == 0
    assert "workers.py::Repository" in result.output


def test_external_dotted_call_is_counted_and_not_stored(tmp_path: Path) -> None:
    source = tmp_path / "main.py"
    source.write_text("import requests\nrequests.api.get()\n", encoding="utf-8")

    resolution = resolve_calls(tmp_path)

    assert resolution.stats.external_package == 1
    assert resolution.stats.unknown_receiver == 0
    assert resolution.edges == ()