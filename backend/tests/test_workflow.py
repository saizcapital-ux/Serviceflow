"""Unit tests for the work-order state machine (pure logic, no DB)."""
from app.models import WorkOrderStatus as S
from app.services import workflow


def test_valid_forward_transition():
    assert workflow.can_transition(S.intake, S.inspection)
    assert workflow.can_transition(S.approved, S.in_repair)
    assert workflow.can_transition(S.ready, S.shipped)


def test_invalid_transitions_rejected():
    assert not workflow.can_transition(S.intake, S.shipped)      # can't skip the pipeline
    assert not workflow.can_transition(S.closed, S.in_repair)    # terminal
    assert not workflow.can_transition(S.ready, S.intake)        # no going backwards to intake


def test_same_status_is_not_a_transition():
    assert not workflow.can_transition(S.in_repair, S.in_repair)


def test_terminal_states_have_no_exits():
    assert workflow.ALLOWED_TRANSITIONS[S.closed] == set()
    assert workflow.ALLOWED_TRANSITIONS[S.cancelled] == set()


def test_quote_totals():
    class L:
        def __init__(self, t):
            self.line_total = t

    subtotal, tax, total = workflow.compute_quote_totals([L(100), L(50.5)], tax_rate=0.10)
    assert subtotal == 150.5
    assert tax == 15.05
    assert total == 165.55
