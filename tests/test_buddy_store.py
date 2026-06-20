"""Tests for the buddy system store. Run with: pytest"""

import pytest

from hearth.buddies.store import BuddyStore


@pytest.fixture
def store(tmp_path):
    return BuddyStore(tmp_path / "buddies")


# -- pairing -------------------------------------------------------------------

def test_pair_creates_bidirectional_link(store):
    msg = store.pair("alice", "bob")
    assert "alice" in msg and "bob" in msg
    assert store.buddy_of("alice") == "bob"
    assert store.buddy_of("bob") == "alice"


def test_pair_self_rejected(store):
    msg = store.pair("alice", "alice")
    assert "cannot" in msg.lower()
    assert store.buddy_of("alice") is None


def test_pair_idempotent(store):
    store.pair("alice", "bob")
    msg = store.pair("alice", "bob")
    assert "already" in msg.lower()


def test_pair_blocks_when_already_paired(store):
    store.pair("alice", "bob")
    msg = store.pair("alice", "carol")
    assert "already paired" in msg.lower()


def test_pair_blocks_buddy_who_is_taken(store):
    store.pair("alice", "bob")
    msg = store.pair("carol", "bob")
    assert "already has" in msg.lower()


def test_unpair_removes_both_sides(store):
    store.pair("alice", "bob")
    msg = store.unpair("alice")
    assert store.buddy_of("alice") is None
    assert store.buddy_of("bob") is None
    assert "removed" in msg.lower()


def test_unpair_without_buddy(store):
    msg = store.unpair("alice")
    assert "no buddy" in msg.lower()


def test_list_pairs(store):
    store.pair("alice", "bob")
    store.pair("carol", "dave")
    pairs = store.list_pairs()
    assert len(pairs) == 2


# -- goals ---------------------------------------------------------------------

def test_set_goal_requires_buddy(store):
    msg = store.set_goal("alice", "finish the report")
    assert "no buddy" in msg.lower()


def test_set_and_list_goal(store):
    store.pair("alice", "bob")
    store.set_goal("alice", "finish the report")
    goals = store.get_goals("alice")
    assert len(goals) == 1
    assert goals[0]["text"] == "finish the report"
    assert goals[0]["set_by"] == "alice"
    assert not goals[0]["done"]


def test_set_multiple_goals(store):
    store.pair("alice", "bob")
    store.set_goal("alice", "goal A")
    store.set_goal("bob", "goal B")
    goals = store.get_goals("alice")
    assert len(goals) == 2


def test_complete_goal(store):
    store.pair("alice", "bob")
    store.set_goal("alice", "finish the report")
    msg = store.complete_goal("alice", 0)
    assert "done" in msg.lower()
    assert store.get_goals("alice")[0]["done"] is True


def test_complete_goal_out_of_range(store):
    store.pair("alice", "bob")
    store.set_goal("alice", "finish the report")
    msg = store.complete_goal("alice", 5)
    assert "no goal" in msg.lower()


def test_complete_goal_without_buddy(store):
    msg = store.complete_goal("alice", 0)
    assert "no buddy" in msg.lower()


# -- notes ---------------------------------------------------------------------

def test_leave_note_requires_buddy(store):
    msg = store.leave_note("alice", "good luck!")
    assert "no buddy" in msg.lower()


def test_leave_and_collect_note(store):
    store.pair("alice", "bob")
    store.leave_note("alice", "great work yesterday!")
    notes = store.pop_notes("bob")
    assert len(notes) == 1
    assert notes[0]["text"] == "great work yesterday!"
    assert notes[0]["from_id"] == "alice"
    # cleared after pop
    assert store.pop_notes("bob") == []


def test_peek_does_not_clear_notes(store):
    store.pair("alice", "bob")
    store.leave_note("alice", "hello")
    store.peek_notes("bob")
    assert len(store.pop_notes("bob")) == 1


def test_multiple_notes_stack(store):
    store.pair("alice", "bob")
    store.leave_note("alice", "note 1")
    store.leave_note("alice", "note 2")
    notes = store.pop_notes("bob")
    assert len(notes) == 2


# -- status report -------------------------------------------------------------

def test_status_no_buddy(store):
    report = store.status_report("alice")
    assert "no buddy" in report.lower()


def test_status_with_buddy_and_goals(store):
    store.pair("alice", "bob")
    store.set_goal("alice", "study for exam")
    store.leave_note("alice", "you got this!")
    report = store.status_report("bob")
    assert "alice" in report
    assert "study for exam" in report
    assert "you got this!" in report


def test_status_shows_completion_marks(store):
    store.pair("alice", "bob")
    store.set_goal("alice", "task one")
    store.complete_goal("alice", 0)
    report = store.status_report("alice")
    assert "[x]" in report
