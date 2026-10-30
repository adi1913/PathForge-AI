"""
Importing every model module here is what makes `Base.metadata` complete.
Alembic's env.py and any `Base.metadata.create_all()` call both rely on
`import app.models` having run first - a model defined but never imported
anywhere is invisible to both and silently missing from migrations.
"""

from app.db.base import Base
from app.models.application import ApplicationEvent, JobApplication
from app.models.assessment import (
    Assessment,
    AssessmentAnswer,
    AssessmentAttempt,
    AssessmentEvidence,
    Question,
)
from app.models.document import Document, DocumentChunk
from app.models.job_description import JobDescription, JobDescriptionSkill
from app.models.learning_resource import LearningResource
from app.models.mcp_log import MCPToolLog
from app.models.mentor import MentorMessage, MentorSession
from app.models.profile import Profile
from app.models.progress import ProgressEvent
from app.models.project import GithubRepository, Project, ProjectEvaluation
from app.models.repo_evidence import RepositoryEvaluation, SkillEvidence
from app.models.roadmap import Roadmap, RoadmapItem
from app.models.skill import Skill, SkillPrerequisite, UserSkill
from app.models.skill_gap import SkillGap
from app.models.target_role import TargetRole, TargetRoleSkill
from app.models.user import User

__all__ = [
    "ApplicationEvent",
    "Assessment",
    "AssessmentAnswer",
    "AssessmentAttempt",
    "AssessmentEvidence",
    "Base",
    "Document",
    "DocumentChunk",
    "GithubRepository",
    "JobApplication",
    "JobDescription",
    "JobDescriptionSkill",
    "LearningResource",
    "MCPToolLog",
    "MentorMessage",
    "MentorSession",
    "Profile",
    "ProgressEvent",
    "Project",
    "ProjectEvaluation",
    "Question",
    "RepositoryEvaluation",
    "Roadmap",
    "RoadmapItem",
    "Skill",
    "SkillEvidence",
    "SkillGap",
    "SkillPrerequisite",
    "TargetRole",
    "TargetRoleSkill",
    "User",
    "UserSkill",
]
