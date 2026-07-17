"""Intelligence Agent for HackOps AI.

Analyzes hackathons using Amazon Bedrock (Nova Micro) to generate strategic
recommendations. Falls back to deterministic mock when Bedrock is unavailable.

This agent never writes to Notion or any external storage.
"""

import json
import logging
from dataclasses import asdict
from json import JSONDecodeError
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from models.hackathon import EnrichedHackathon, Hackathon, IntelligenceResult

logger = logging.getLogger(__name__)

# Bedrock configuration
_BEDROCK_REGION = "ap-south-1"
_MODEL_ID = "amazon.nova-micro-v1:0"
_BEDROCK_TIMEOUT = 10  # seconds per invocation (requirement 7.1)

# Boto3 config with timeout
_BOTO_CONFIG = Config(
    region_name=_BEDROCK_REGION,
    read_timeout=_BEDROCK_TIMEOUT,
    connect_timeout=_BEDROCK_TIMEOUT,
    retries={"max_attempts": 0},
)

# Valid values for validation
_VALID_PRIORITIES = {"High", "Medium", "Low"}
_VALID_DIFFICULTIES = {"Easy", "Medium", "Hard"}


def analyze_batch(hackathons: list[Hackathon]) -> list[EnrichedHackathon]:
    """Analyze all hackathons, enriching each with AI insights.

    Returns a list of the same length and order as input. For an empty
    input list, returns an empty list.

    If AWS credentials are missing or Bedrock client cannot be created,
    falls back to mock analysis for the entire batch (requirement 7.1).

    Args:
        hackathons: List of validated Hackathon objects.

    Returns:
        List of EnrichedHackathon objects with intelligence fields populated.
    """
    results: list[EnrichedHackathon] = []

    # Check if Bedrock is available by attempting client creation (requirement 7.1)
    bedrock_available = _check_bedrock_available()

    for hackathon in hackathons:
        if bedrock_available:
            intelligence = analyze_single(hackathon)
        else:
            intelligence = _mock_analysis(hackathon)
        enriched = _merge(hackathon, intelligence)
        results.append(enriched)

    return results


def _check_bedrock_available() -> bool:
    """Check if Bedrock credentials are available.

    Attempts to create a boto3 client for Bedrock. If credentials are
    missing or invalid, returns False so the batch can fall back to mock.

    Returns:
        True if Bedrock client can be created, False otherwise.
    """
    try:
        boto3.client("bedrock-runtime", config=_BOTO_CONFIG)
        return True
    except (BotoCoreError, ClientError, Exception) as e:
        logger.warning("Bedrock unavailable (credentials missing or invalid): %s. Using mock for entire batch.", e)
        return False


def analyze_single(hackathon: Hackathon) -> IntelligenceResult:
    """Analyze a single hackathon via Bedrock with mock fallback.

    Attempts to call Amazon Bedrock Nova Micro. On any failure (network,
    credentials, invalid response, timeout), falls back to deterministic
    mock analysis.

    Args:
        hackathon: A validated Hackathon object.

    Returns:
        IntelligenceResult with AI-generated or mock insights.
    """
    try:
        hackathon_json = _serialize_hackathon(hackathon)
        result = _call_bedrock(hackathon_json)
        return result
    except (BotoCoreError, ClientError, JSONDecodeError, ValueError, KeyError, Exception) as e:
        logger.warning("Bedrock analysis failed for '%s': %s. Using mock.", hackathon.title, e)
        return _mock_analysis(hackathon)


def _call_bedrock(hackathon_json: str) -> IntelligenceResult:
    """Call Amazon Bedrock Nova Micro for hackathon analysis.

    Sends a structured prompt requesting JSON output with required fields.
    Parses and validates the response before constructing IntelligenceResult.

    Args:
        hackathon_json: Serialized hackathon data as JSON string.

    Returns:
        Parsed and validated IntelligenceResult.

    Raises:
        BotoCoreError: AWS SDK errors (credentials, network).
        ClientError: Bedrock service errors.
        JSONDecodeError: Response is not valid JSON.
        ValueError: Response fields fail validation.
        KeyError: Required fields missing from response.
    """
    client = boto3.client("bedrock-runtime", config=_BOTO_CONFIG)

    prompt = (
        "You are HackOps AI, a hackathon strategy advisor. "
        "Analyze the following hackathon and return ONLY valid JSON with these exact fields:\n"
        "- priority: one of \"High\", \"Medium\", or \"Low\"\n"
        "- difficulty: one of \"Easy\", \"Medium\", or \"Hard\"\n"
        "- winning_probability: integer from 0 to 100\n"
        "- recommended_stack: list of 1-10 technology strings\n"
        "- recommended_team_size: integer from 1 to 20\n"
        "- execution_strategy: non-empty string (max 2000 chars)\n"
        "- summary: non-empty string (max 500 chars)\n\n"
        "Return ONLY the JSON object, no markdown or extra text.\n\n"
        f"Hackathon data:\n{hackathon_json}"
    )

    request_body = json.dumps({
        "messages": [{"role": "user", "content": [{"text": prompt}]}],
        "inferenceConfig": {"maxTokens": 512, "temperature": 0.3},
    })

    response = client.invoke_model(
        modelId=_MODEL_ID,
        contentType="application/json",
        accept="application/json",
        body=request_body,
    )

    response_body = json.loads(response["body"].read())
    content_text = response_body["output"]["message"]["content"][0]["text"]

    # Strip markdown code fences if present
    cleaned = content_text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        # Remove first line (```json or ```) and last line (```)
        lines = [l for l in lines[1:] if not l.strip().startswith("```")]
        cleaned = "\n".join(lines)

    parsed = json.loads(cleaned)
    return _validate_and_build(parsed)


def _validate_and_build(parsed: dict[str, Any]) -> IntelligenceResult:
    """Validate parsed Bedrock response and build IntelligenceResult.

    Args:
        parsed: Dictionary parsed from Bedrock JSON response.

    Returns:
        Validated IntelligenceResult.

    Raises:
        KeyError: If required fields are missing.
        ValueError: If field values are invalid.
    """
    # Extract required fields (KeyError raised if missing)
    priority = parsed["priority"]
    difficulty = parsed["difficulty"]
    winning_probability = int(parsed["winning_probability"])
    recommended_stack = parsed["recommended_stack"]
    recommended_team_size = int(parsed["recommended_team_size"])
    execution_strategy = str(parsed["execution_strategy"])
    summary = str(parsed["summary"])

    # Validate priority
    if priority not in _VALID_PRIORITIES:
        raise ValueError(f"Invalid priority: {priority}")

    # Validate difficulty
    if difficulty not in _VALID_DIFFICULTIES:
        raise ValueError(f"Invalid difficulty: {difficulty}")

    # Validate winning_probability range
    if not (0 <= winning_probability <= 100):
        raise ValueError(f"winning_probability out of range: {winning_probability}")

    # Validate recommended_stack
    if not isinstance(recommended_stack, list) or len(recommended_stack) == 0:
        raise ValueError("recommended_stack must be a non-empty list")
    if len(recommended_stack) > 10:
        recommended_stack = recommended_stack[:10]
    recommended_stack = [str(s) for s in recommended_stack if s]
    if not recommended_stack:
        raise ValueError("recommended_stack contains no valid entries")

    # Validate recommended_team_size
    if not (1 <= recommended_team_size <= 20):
        raise ValueError(f"recommended_team_size out of range: {recommended_team_size}")

    # Validate execution_strategy
    if not execution_strategy.strip():
        raise ValueError("execution_strategy must be non-empty")
    if len(execution_strategy) > 2000:
        execution_strategy = execution_strategy[:2000]

    # Validate summary
    if not summary.strip():
        raise ValueError("summary must be non-empty")
    if len(summary) > 500:
        summary = summary[:500]

    return IntelligenceResult(
        priority=priority,
        difficulty=difficulty,
        winning_probability=winning_probability,
        recommended_stack=recommended_stack,
        recommended_team_size=recommended_team_size,
        execution_strategy=execution_strategy,
        summary=summary,
    )


def _mock_analysis(hackathon: Hackathon) -> IntelligenceResult:
    """Deterministic fallback when Bedrock is unavailable.

    Produces consistent results based on hackathon fields (prize and themes).
    Identical input always yields identical output (requirement 7.3).

    Logic:
    - If prize contains "$": High priority, Hard difficulty, 30% winning prob
    - Elif themes is non-empty: Medium priority, Medium difficulty, 50% winning prob
    - Else: Low priority, Easy difficulty, 70% winning prob

    Args:
        hackathon: A Hackathon object to generate mock analysis for.

    Returns:
        IntelligenceResult with deterministic values based on prize/themes.
    """
    # Deterministic priority based on prize presence
    if hackathon.prize and "$" in (hackathon.prize or ""):
        priority = "High"
        difficulty = "Hard"
        winning_prob = 30
    elif hackathon.themes:
        priority = "Medium"
        difficulty = "Medium"
        winning_prob = 50
    else:
        priority = "Low"
        difficulty = "Easy"
        winning_prob = 70

    return IntelligenceResult(
        priority=priority,
        difficulty=difficulty,
        winning_probability=winning_prob,
        recommended_stack=["Python", "FastAPI", "React"],
        recommended_team_size=3,
        execution_strategy="Research themes, build MVP in first 48h, polish last 24h.",
        summary=f"Hackathon on {hackathon.platform} - {priority} priority.",
    )


def _serialize_hackathon(hackathon: Hackathon) -> str:
    """Serialize a Hackathon to JSON string for the Bedrock prompt.

    Args:
        hackathon: Hackathon object to serialize.

    Returns:
        JSON string representation of the hackathon.
    """
    data = asdict(hackathon)
    return json.dumps(data, indent=2, default=str)


def _merge(hackathon: Hackathon, intelligence: IntelligenceResult) -> EnrichedHackathon:
    """Merge Hackathon fields with IntelligenceResult into EnrichedHackathon.

    Preserves all original hackathon fields unchanged and adds intelligence
    analysis fields.

    Args:
        hackathon: Original Hackathon object.
        intelligence: Analysis result from Bedrock or mock.

    Returns:
        EnrichedHackathon with all fields populated.
    """
    return EnrichedHackathon(
        # Discovery fields
        title=hackathon.title,
        platform=hackathon.platform,
        registration_url=hackathon.registration_url,
        registration_deadline=hackathon.registration_deadline,
        submission_deadline=hackathon.submission_deadline,
        organizer=hackathon.organizer,
        themes=hackathon.themes,
        mode=hackathon.mode,
        location=hackathon.location,
        prize=hackathon.prize,
        team_size=hackathon.team_size,
        # Intelligence fields
        priority=intelligence.priority,
        difficulty=intelligence.difficulty,
        winning_probability=intelligence.winning_probability,
        recommended_stack=intelligence.recommended_stack,
        recommended_team_size=intelligence.recommended_team_size,
        execution_strategy=intelligence.execution_strategy,
        summary=intelligence.summary,
    )
