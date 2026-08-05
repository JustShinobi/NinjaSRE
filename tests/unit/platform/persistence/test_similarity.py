"""The scoring the in-memory index sorts by.

Worth its own file because the port makes a promise about it that callers rely
on and no repository test would catch if it broke: scores are *similarities* in
``[0.0, 1.0]``, so larger is nearer, whatever distance operator a backend used
underneath. Get the direction wrong and every search still returns results —
just the least similar ones, ranked confidently.
"""

from __future__ import annotations

import pytest

from platform.persistence.fakes.vector_index import cosine_similarity

pytestmark = pytest.mark.unit


def test_a_vector_is_maximally_similar_to_itself() -> None:
    assert cosine_similarity((1.0, 2.0, 3.0), (1.0, 2.0, 3.0)) == pytest.approx(1.0)


def test_direction_is_what_matters_not_magnitude() -> None:
    assert cosine_similarity((1.0, 0.0), (7.0, 0.0)) == pytest.approx(1.0)


def test_the_opposite_direction_scores_zero_rather_than_minus_one() -> None:
    # Rescaled to the unit interval so a caller can treat the score as a
    # confidence without knowing how the index was built.
    assert cosine_similarity((1.0, 0.0), (-1.0, 0.0)) == pytest.approx(0.0)


def test_orthogonal_vectors_land_in_the_middle() -> None:
    assert cosine_similarity((1.0, 0.0), (0.0, 1.0)) == pytest.approx(0.5)


def test_a_zero_vector_has_no_direction_to_compare() -> None:
    # Rather than dividing by zero. An all-zero embedding is a model that
    # failed, and it should sort last rather than crash the search.
    assert cosine_similarity((0.0, 0.0), (1.0, 0.0)) == 0.0
    assert cosine_similarity((0.0, 0.0), (0.0, 0.0)) == 0.0


def test_scores_stay_inside_the_unit_interval() -> None:
    vectors = [(1.0, 0.0), (0.0, 1.0), (-1.0, 0.0), (0.5, -0.5), (-3.0, 4.0)]

    for left in vectors:
        for right in vectors:
            assert 0.0 <= cosine_similarity(left, right) <= 1.0


def test_comparing_different_widths_is_a_bug_not_a_score() -> None:
    # The index refuses this before it gets here. If something ever gets past
    # that, silently scoring the shared prefix would be worse than failing.
    with pytest.raises(ValueError, match="argument 2 is shorter"):
        cosine_similarity((1.0, 0.0, 0.0), (1.0, 0.0))
