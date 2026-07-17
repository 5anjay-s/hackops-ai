"""Data models for HackOps AI pipeline."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Hackathon:
    """Normalized hackathon data from Discovery Agent.

    Represents a single hackathon listing with metadata extracted
    from supported platforms (Devpost, Devfolio, Unstop).
    """

    title: str
    platform: str  # "Devpost" | "Devfolio" | "Unstop"
    registration_url: str
    registration_deadline: Optional[str] = None  # ISO 8601 (YYYY-MM-DD) or None
    submission_deadline: Optional[str] = None  # ISO 8601 (YYYY-MM-DD) or None
    organizer: Optional[str] = None
    themes: list[str] = field(default_factory=list)
    mode: Optional[str] = None  # "online" | "offline" | "hybrid" | None
    location: Optional[str] = None
    prize: Optional[str] = None
    team_size: Optional[str] = None


@dataclass
class IntelligenceResult:
    """AI-generated analysis for a single hackathon.

    Produced by the Intelligence Agent via Amazon Bedrock or
    deterministic mock fallback.
    """

    priority: str  # "High" | "Medium" | "Low"
    difficulty: str  # "Easy" | "Medium" | "Hard"
    winning_probability: int  # 0-100
    recommended_stack: list[str]
    recommended_team_size: int
    execution_strategy: str
    summary: str


@dataclass
class EnrichedHackathon:
    """Hackathon combined with Intelligence analysis.

    Merges all Discovery fields with all Intelligence fields
    for downstream consumption by the Workspace Agent.
    """

    # Discovery fields
    title: str
    platform: str  # "Devpost" | "Devfolio" | "Unstop"
    registration_url: str
    registration_deadline: Optional[str] = None
    submission_deadline: Optional[str] = None
    organizer: Optional[str] = None
    themes: list[str] = field(default_factory=list)
    mode: Optional[str] = None  # "online" | "offline" | "hybrid" | None
    location: Optional[str] = None
    prize: Optional[str] = None
    team_size: Optional[str] = None
    # Intelligence fields
    priority: str = "Medium"  # "High" | "Medium" | "Low"
    difficulty: str = "Medium"  # "Easy" | "Medium" | "Hard"
    winning_probability: int = 50  # 0-100
    recommended_stack: list[str] = field(default_factory=list)
    recommended_team_size: int = 3
    execution_strategy: str = ""
    summary: str = ""


@dataclass
class SyncResult:
    """Summary of Workspace Agent sync operations.

    Invariant: new + updated + failed == processed.
    Archived is tracked separately and not included in processed total.
    """

    processed: int
    new: int
    updated: int
    archived: int
    failed: int
