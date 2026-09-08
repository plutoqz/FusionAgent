from __future__ import annotations

from benchmark_platform.projections import project_condition
from benchmark_platform.selection import InterfaceCandidate, SelectionError, screen_interface_candidates
from tests.test_benchmark_method_selection_projections import _bundle, _context


def test_interface_screen_is_deterministic_and_does_not_use_performance_scores():
    candidates = (
        InterfaceCandidate(interface_id="raw_full_kg", complexity_rank=3, token_cap=50000, information_fields=("contracts", "quality_policies")),
        InterfaceCandidate(interface_id="task_conditioned_typed", complexity_rank=1, token_cap=50000, information_fields=("contracts", "quality_policies")),
        InterfaceCandidate(interface_id="capped_query_on_demand", complexity_rank=2, token_cap=50000, information_fields=("contracts", "quality_policies")),
    )
    first = screen_interface_candidates(_bundle(), _context(), candidates, request={"product": "road"}, output_schema={"type": "object"})
    second = screen_interface_candidates(_bundle(), _context(), candidates, request={"product": "road"}, output_schema={"type": "object"})
    assert first == second
    assert first.performance_scores_used is False
    assert first.ordered_candidate_ids


def test_screen_rejects_empty_or_unclosed_candidates():
    import pytest
    with pytest.raises(SelectionError, match="at least one"):
        screen_interface_candidates(_bundle(), _context(), (), request={}, output_schema={})
    with pytest.raises(SelectionError, match="no full-contract"):
        screen_interface_candidates(
            _bundle(), _context(),
            (InterfaceCandidate(interface_id="capped_query_on_demand", complexity_rank=1, token_cap=1, information_fields=("contracts",)),),
            request={}, output_schema={},
        )
