"""Property-based tests for the Intelligence Agent.

Covers Properties 6-9 from the design document:
- Property 6: Intelligence batch length preservation
- Property 7: Intelligence field validity
- Property 8: Intelligence non-destructive enrichment
- Property 9: Mock analysis determinism

Uses hypothesis to generate Hackathon objects and verify universal properties
hold across all valid inputs.
"""

from unittest.mock import patch

from hypothesis import given, settings
from hypothesis import strategies as st

from agents.intelligence_agent import analyze_batch, _mock_analysis, _merge, _check_bedrock_available
from models.hackathon import EnrichedHackathon, Hackathon, IntelligenceResult


# --- Strategies ---

PLATFORMS = st.sampled_from(["Devpost", "Devfolio", "Unstop"])

_url_slugs = st.text(
    alphabet=st.characters(whitelist_categories=("Ll", "Nd"), whitelist_characters="-"),
    min_size=1,
    max_size=30,
)

VALID_URLS = _url_slugs.map(lambda slug: f"https://example.com/{slug}")

HACKATHON_STRATEGY = st.builds(
    Hackathon,
    title=st.text(min_size=1, max_size=50).filter(lambda t: t.strip()),
    platform=PLATFORMS,
    registration_url=VALID_URLS,
    registration_deadline=st.one_of(st.none(), st.just("2025-06-01")),
    submission_deadline=st.one_of(st.none(), st.just("2025-07-01")),
    organizer=st.one_of(st.none(), st.text(min_size=1, max_size=30)),
    themes=st.lists(st.text(min_size=1, max_size=20), max_size=5),
    mode=st.one_of(st.none(), st.sampled_from(["online", "offline", "hybrid"])),
    location=st.one_of(st.none(), st.text(min_size=1, max_size=30)),
    prize=st.one_of(st.none(), st.text(min_size=1, max_size=50)),
    team_size=st.one_of(st.none(), st.text(min_size=1, max_size=20)),
)

HACKATHON_LIST_STRATEGY = st.lists(HACKATHON_STRATEGY, min_size=0, max_size=10)


# --- Property 6: Intelligence batch length preservation ---


class TestBatchLengthPreservation:
    """Property 6: Intelligence batch length preservation.

    For any input list of Hackathon objects, analyze_batch() returns a list
    of EnrichedHackathon objects of exactly the same length.

    **Validates: Requirements 6.1, 12.3**
    """

    @given(hackathons=HACKATHON_LIST_STRATEGY)
    @settings(max_examples=200)
    @patch("agents.intelligence_agent._check_bedrock_available", return_value=False)
    def test_output_length_equals_input_length(self, mock_bedrock, hackathons):
        """**Validates: Requirements 6.1, 12.3**

        For any list of Hackathon objects, the output length of analyze_batch
        must equal the input length.
        """
        results = analyze_batch(hackathons)

        assert len(results) == len(hackathons), (
            f"Output length {len(results)} != input length {len(hackathons)}"
        )

    @given(hackathons=HACKATHON_LIST_STRATEGY)
    @settings(max_examples=200)
    @patch("agents.intelligence_agent._check_bedrock_available", return_value=False)
    def test_output_contains_only_enriched_hackathons(self, mock_bedrock, hackathons):
        """**Validates: Requirements 6.1, 12.3**

        Every element in the output of analyze_batch must be an EnrichedHackathon.
        """
        results = analyze_batch(hackathons)

        for i, result in enumerate(results):
            assert isinstance(result, EnrichedHackathon), (
                f"Element {i} is {type(result).__name__}, expected EnrichedHackathon"
            )


# --- Property 7: Intelligence field validity ---


class TestFieldValidity:
    """Property 7: Intelligence field validity.

    For any Hackathon input, _mock_analysis produces IntelligenceResult with
    all fields within valid ranges.

    **Validates: Requirements 6.3, 7.4, 7.5**
    """

    @given(hackathon=HACKATHON_STRATEGY)
    @settings(max_examples=200)
    def test_priority_is_valid(self, hackathon):
        """**Validates: Requirements 6.3, 7.4, 7.5**

        priority must be one of "High", "Medium", or "Low".
        """
        result = _mock_analysis(hackathon)
        assert result.priority in {"High", "Medium", "Low"}, (
            f"Invalid priority: {result.priority}"
        )

    @given(hackathon=HACKATHON_STRATEGY)
    @settings(max_examples=200)
    def test_difficulty_is_valid(self, hackathon):
        """**Validates: Requirements 6.3, 7.4, 7.5**

        difficulty must be one of "Easy", "Medium", or "Hard".
        """
        result = _mock_analysis(hackathon)
        assert result.difficulty in {"Easy", "Medium", "Hard"}, (
            f"Invalid difficulty: {result.difficulty}"
        )

    @given(hackathon=HACKATHON_STRATEGY)
    @settings(max_examples=200)
    def test_winning_probability_in_range(self, hackathon):
        """**Validates: Requirements 6.3, 7.4, 7.5**

        winning_probability must be an integer in [0, 100].
        """
        result = _mock_analysis(hackathon)
        assert isinstance(result.winning_probability, int), (
            f"winning_probability is {type(result.winning_probability).__name__}, expected int"
        )
        assert 0 <= result.winning_probability <= 100, (
            f"winning_probability {result.winning_probability} out of range [0, 100]"
        )

    @given(hackathon=HACKATHON_STRATEGY)
    @settings(max_examples=200)
    def test_recommended_stack_non_empty(self, hackathon):
        """**Validates: Requirements 6.3, 7.4, 7.5**

        recommended_stack must be a non-empty list.
        """
        result = _mock_analysis(hackathon)
        assert isinstance(result.recommended_stack, list), (
            f"recommended_stack is {type(result.recommended_stack).__name__}, expected list"
        )
        assert len(result.recommended_stack) > 0, "recommended_stack must be non-empty"

    @given(hackathon=HACKATHON_STRATEGY)
    @settings(max_examples=200)
    def test_recommended_team_size_positive(self, hackathon):
        """**Validates: Requirements 6.3, 7.4, 7.5**

        recommended_team_size must be a positive integer.
        """
        result = _mock_analysis(hackathon)
        assert isinstance(result.recommended_team_size, int), (
            f"recommended_team_size is {type(result.recommended_team_size).__name__}, expected int"
        )
        assert result.recommended_team_size > 0, (
            f"recommended_team_size {result.recommended_team_size} is not positive"
        )

    @given(hackathon=HACKATHON_STRATEGY)
    @settings(max_examples=200)
    def test_execution_strategy_non_empty_string(self, hackathon):
        """**Validates: Requirements 6.3, 7.4, 7.5**

        execution_strategy must be a non-empty string.
        """
        result = _mock_analysis(hackathon)
        assert isinstance(result.execution_strategy, str), (
            f"execution_strategy is {type(result.execution_strategy).__name__}, expected str"
        )
        assert len(result.execution_strategy) > 0, "execution_strategy must be non-empty"

    @given(hackathon=HACKATHON_STRATEGY)
    @settings(max_examples=200)
    def test_summary_non_empty_string(self, hackathon):
        """**Validates: Requirements 6.3, 7.4, 7.5**

        summary must be a non-empty string.
        """
        result = _mock_analysis(hackathon)
        assert isinstance(result.summary, str), (
            f"summary is {type(result.summary).__name__}, expected str"
        )
        assert len(result.summary) > 0, "summary must be non-empty"


# --- Property 8: Intelligence non-destructive enrichment ---


class TestNonDestructiveEnrichment:
    """Property 8: Intelligence non-destructive enrichment.

    For any Hackathon input, the corresponding EnrichedHackathon output
    preserves all original Hackathon fields unchanged.

    **Validates: Requirements 6.4**
    """

    @given(hackathons=st.lists(HACKATHON_STRATEGY, min_size=1, max_size=10))
    @settings(max_examples=200)
    @patch("agents.intelligence_agent._check_bedrock_available", return_value=False)
    def test_all_hackathon_fields_preserved(self, mock_bedrock, hackathons):
        """**Validates: Requirements 6.4**

        All original Hackathon fields must be preserved unchanged in the
        EnrichedHackathon output after analyze_batch.
        """
        results = analyze_batch(hackathons)

        for hackathon, enriched in zip(hackathons, results):
            assert enriched.title == hackathon.title, (
                f"title changed: {hackathon.title!r} -> {enriched.title!r}"
            )
            assert enriched.platform == hackathon.platform, (
                f"platform changed: {hackathon.platform!r} -> {enriched.platform!r}"
            )
            assert enriched.registration_url == hackathon.registration_url, (
                f"registration_url changed: {hackathon.registration_url!r} -> {enriched.registration_url!r}"
            )
            assert enriched.registration_deadline == hackathon.registration_deadline, (
                f"registration_deadline changed: {hackathon.registration_deadline!r} -> {enriched.registration_deadline!r}"
            )
            assert enriched.submission_deadline == hackathon.submission_deadline, (
                f"submission_deadline changed: {hackathon.submission_deadline!r} -> {enriched.submission_deadline!r}"
            )
            assert enriched.organizer == hackathon.organizer, (
                f"organizer changed: {hackathon.organizer!r} -> {enriched.organizer!r}"
            )
            assert enriched.themes == hackathon.themes, (
                f"themes changed: {hackathon.themes!r} -> {enriched.themes!r}"
            )
            assert enriched.mode == hackathon.mode, (
                f"mode changed: {hackathon.mode!r} -> {enriched.mode!r}"
            )
            assert enriched.location == hackathon.location, (
                f"location changed: {hackathon.location!r} -> {enriched.location!r}"
            )
            assert enriched.prize == hackathon.prize, (
                f"prize changed: {hackathon.prize!r} -> {enriched.prize!r}"
            )
            assert enriched.team_size == hackathon.team_size, (
                f"team_size changed: {hackathon.team_size!r} -> {enriched.team_size!r}"
            )


# --- Property 9: Mock analysis determinism ---


class TestMockAnalysisDeterminism:
    """Property 9: Mock analysis determinism.

    For any Hackathon input, calling _mock_analysis twice with the same
    input produces identical IntelligenceResult objects.

    **Validates: Requirements 7.3**
    """

    @given(hackathon=HACKATHON_STRATEGY)
    @settings(max_examples=200)
    def test_identical_input_yields_identical_output(self, hackathon):
        """**Validates: Requirements 7.3**

        Calling _mock_analysis twice on the same Hackathon must produce
        identical IntelligenceResult values.
        """
        result1 = _mock_analysis(hackathon)
        result2 = _mock_analysis(hackathon)

        assert result1.priority == result2.priority, (
            f"priority differs: {result1.priority} vs {result2.priority}"
        )
        assert result1.difficulty == result2.difficulty, (
            f"difficulty differs: {result1.difficulty} vs {result2.difficulty}"
        )
        assert result1.winning_probability == result2.winning_probability, (
            f"winning_probability differs: {result1.winning_probability} vs {result2.winning_probability}"
        )
        assert result1.recommended_stack == result2.recommended_stack, (
            f"recommended_stack differs: {result1.recommended_stack} vs {result2.recommended_stack}"
        )
        assert result1.recommended_team_size == result2.recommended_team_size, (
            f"recommended_team_size differs: {result1.recommended_team_size} vs {result2.recommended_team_size}"
        )
        assert result1.execution_strategy == result2.execution_strategy, (
            f"execution_strategy differs: {result1.execution_strategy!r} vs {result2.execution_strategy!r}"
        )
        assert result1.summary == result2.summary, (
            f"summary differs: {result1.summary!r} vs {result2.summary!r}"
        )
