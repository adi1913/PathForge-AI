"""
Enums shared across models. All are mapped with `native_enum=False` (see
usage in each model file) so they land as VARCHAR + CHECK constraint on
every backend, rather than Postgres-only native ENUM types — that keeps
`alembic downgrade` symmetric and SQLite behavior identical to Postgres.
"""

import enum


class SkillLevel(str, enum.Enum):
    NONE = "none"
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"


class EvidenceSource(str, enum.Enum):
    RESUME = "resume"
    ASSESSMENT = "assessment"
    PROJECT = "project"
    GITHUB = "github"
    MANUAL = "manual"
    MENTOR_EVALUATION = "mentor_evaluation"


class ImportanceLevel(str, enum.Enum):
    REQUIRED = "required"
    PREFERRED = "preferred"
    NICE_TO_HAVE = "nice_to_have"


class SkillGapStatus(str, enum.Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    CLOSED = "closed"
    DEFERRED = "deferred"


class RoadmapStatus(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class RoadmapItemType(str, enum.Enum):
    SKILL = "skill"
    LEARNING_RESOURCE = "learning_resource"
    PROJECT = "project"
    ASSESSMENT = "assessment"


class RoadmapItemStatus(str, enum.Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    BLOCKED = "blocked"


class Difficulty(str, enum.Enum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class ResourceType(str, enum.Enum):
    COURSE = "course"
    DOCUMENTATION = "documentation"
    TUTORIAL = "tutorial"
    PROJECT = "project"
    VIDEO = "video"
    ARTICLE = "article"


class AssessmentType(str, enum.Enum):
    QUIZ = "quiz"
    CODING = "coding"
    MIXED = "mixed"


class QuestionType(str, enum.Enum):
    MULTIPLE_CHOICE = "multiple_choice"
    SHORT_ANSWER = "short_answer"
    CODING = "coding"


class ProjectStatus(str, enum.Enum):
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class ProgressEventType(str, enum.Enum):
    ITEM_STARTED = "item_started"
    ITEM_COMPLETED = "item_completed"
    ITEM_SKIPPED = "item_skipped"
    ASSESSMENT_PASSED = "assessment_passed"
    ASSESSMENT_FAILED = "assessment_failed"
    ROADMAP_REPLANNED = "roadmap_replanned"
    STREAK_EXTENDED = "streak_extended"
    ITEM_BLOCKED = "item_blocked"  # Phase 9
    ITEM_PROGRESS_UPDATED = "item_progress_updated"  # Phase 9: percent change / reset


class MentorMessageRole(str, enum.Enum):
    USER = "user"
    MENTOR = "mentor"
    SYSTEM = "system"


class MCPToolStatus(str, enum.Enum):
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"


class SkillImportance(str, enum.Enum):
    """Deterministic criticality of a JD-required skill (Phase 7).
    Distinct from ImportanceLevel, which is the requirement *type*."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class GapSeverity(str, enum.Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SkillMatchStatus(str, enum.Enum):
    MATCHED = "matched"
    WEAK = "weak"
    MISSING = "missing"


class ApplicationStatus(str, enum.Enum):  # Phase 10
    INTERESTED = "interested"
    PREPARING = "preparing"
    APPLIED = "applied"
    ASSESSMENT = "assessment"
    INTERVIEW = "interview"
    OFFER = "offer"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


class ApplicationEventType(str, enum.Enum):  # Phase 10
    CREATED = "created"
    STATUS_CHANGED = "status_changed"
    NOTE_ADDED = "note_added"
    DETAILS_UPDATED = "details_updated"


class RepoEvidenceType(str, enum.Enum):  # Phase 11
    DEPENDENCY_MANIFEST = "dependency_manifest"
    LANGUAGE_SHARE = "language_share"
    INFRASTRUCTURE_FILE = "infrastructure_file"
    README_MENTION = "readme_mention"


class AssessmentOutcome(str, enum.Enum):  # Phase 12
    STRONG = "strong"
    PASSED = "passed"
    WEAK = "weak"
    INSUFFICIENT = "insufficient"
