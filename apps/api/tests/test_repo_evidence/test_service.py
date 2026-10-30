import pytest

from app.agent.errors import MCPConnectionError, ToolExecutionError, ToolTimeoutError
from app.models.enums import EvidenceSource, SkillLevel
from app.models.project import GithubRepository
from app.models.repo_evidence import RepositoryEvaluation, SkillEvidence
from app.models.skill import Skill, UserSkill
from app.repo_evidence.collector import MAX_TOOL_CALLS
from app.repo_evidence.errors import (
    EvaluationNotFoundError,
    GitHubMCPUnavailableError,
    GitHubRateLimitedError,
    GitHubUnavailableError,
    InvalidRepositoryUrlError,
    RepositoryNotFoundError,
    UserNotFoundError,
)
from app.repo_evidence.schemas import EvaluateRequest
from app.repo_evidence.service import RepositoryEvaluationService
from tests.test_repo_evidence.helpers import FakeManager, details, seed


async def _evaluate(db, user, manager=None, url="octocat/rag-demo"):
    return await RepositoryEvaluationService(db, manager or FakeManager()).evaluate(
        EvaluateRequest(user_id=user.id, repository_url=url)
    )


def _by_slug(result):
    return {g.skill_slug: g for g in result.evidence}


async def test_public_repository_evidence_is_derived_and_persisted(db_session):
    user, _, _ = seed(db_session)
    result = await _evaluate(db_session, user)
    by = _by_slug(result)
    assert set(by) == {"python", "fastapi", "qdrant", "docker", "ci-cd", "rag"}
    assert {i.evidence_type.value for i in by["fastapi"].items} == {"dependency_manifest", "readme_mention"}
    assert by["fastapi"].aggregate_confidence == 0.55
    assert by["python"].items[0].excerpt == "Python is 90.0% of the repository's bytes"
    assert all(i.limitations and i.confidence <= 0.7 for g in result.evidence for i in g.items)
    assert result.signals["has_tests"] and result.signals["has_ci"] and result.signals["has_license"]
    assert result.data_source == "live" and result.evaluated_at is not None
    assert "Kubernetes".lower() in [t.lower() for t in result.unmatched_technologies]
    assert result.unrecognized_languages == ["TypeScript"]
    assert any("not in the skill catalog" in lim for lim in result.limitations)
    assert any("NOT analyzed" in lim for lim in result.limitations)
    # persisted rows carry the required fields
    row = db_session.query(SkillEvidence).join(Skill).filter(Skill.slug == "qdrant").one()
    assert row.repository_id and row.evaluated_at and row.excerpt and row.limitations and row.data_source == "live"
    repo = db_session.query(GithubRepository).one()
    assert repo.github_url == "https://github.com/octocat/rag-demo" and repo.last_analyzed_at is not None


async def test_no_skill_rows_are_created_for_unmatched_technologies(db_session):
    user, _, _ = seed(db_session)
    before = db_session.query(Skill).count()
    await _evaluate(db_session, user)
    assert db_session.query(Skill).count() == before


async def test_user_skills_are_never_changed(db_session):
    user, _, skills = seed(db_session)
    db_session.add(
        UserSkill(
            user_id=user.id,
            skill_id=skills["python"].id,
            current_level=SkillLevel.BEGINNER,
            confidence=0.3,
            source=EvidenceSource.MANUAL,
        )
    )
    db_session.commit()
    await _evaluate(db_session, user)
    rows = db_session.query(UserSkill).all()
    assert len(rows) == 1  # no row added for FastAPI/Docker/...
    assert (rows[0].current_level, rows[0].confidence, rows[0].source) == (
        SkillLevel.BEGINNER,
        0.3,
        EvidenceSource.MANUAL,
    )


async def test_duplicate_submission_reuses_repository_and_keeps_history(db_session):
    user, _, _ = seed(db_session)
    first = await _evaluate(db_session, user, url="https://github.com/octocat/rag-demo")
    second = await _evaluate(db_session, user, url="octocat/rag-demo")
    third = await _evaluate(db_session, user, url="https://github.com/octocat/rag-demo.git")
    assert (first.reused_repository, second.reused_repository, third.reused_repository) == (False, True, True)
    assert db_session.query(GithubRepository).count() == 1
    assert db_session.query(RepositoryEvaluation).count() == 3
    # latest-only view: evidence listing does not triple-count
    svc = RepositoryEvaluationService(db_session, FakeManager())
    items = svc.list_evidence(user.id, "fastapi")
    assert len(items) == 2 and {i.evidence_type.value for i in items} == {"dependency_manifest", "readme_mention"}
    listing = svc.list_repositories(user.id)
    assert len(listing) == 1 and listing[0].latest_evaluation_id == third.evaluation_id


async def test_ownership_and_unknown_user(db_session):
    user, other, _ = seed(db_session)
    result = await _evaluate(db_session, user)
    svc = RepositoryEvaluationService(db_session, FakeManager())
    assert svc.get_evaluation(result.evaluation_id, user.id).evaluation_id == result.evaluation_id
    with pytest.raises(EvaluationNotFoundError):
        svc.get_evaluation(result.evaluation_id, other.id)
    with pytest.raises(EvaluationNotFoundError):
        svc.get_evaluation("nope", user.id)
    assert svc.list_evidence(other.id, None) == [] and svc.list_repositories(other.id) == []
    with pytest.raises(UserNotFoundError):
        await RepositoryEvaluationService(db_session, FakeManager()).evaluate(
            EvaluateRequest(user_id="ghost", repository_url="a/b")
        )
    # the same repo evaluated by another user is a separate, independent row
    await _evaluate(db_session, other)
    assert db_session.query(GithubRepository).count() == 2


async def test_invalid_url_makes_no_mcp_call(db_session):
    user, _, _ = seed(db_session)
    manager = FakeManager()
    with pytest.raises(InvalidRepositoryUrlError):
        await _evaluate(db_session, user, manager, url="https://evil.example/a/b")
    assert manager.calls == []


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (ToolExecutionError("GitHub resource not found: /repos/a/b"), RepositoryNotFoundError),
        (ToolExecutionError("GitHub API rate limit exceeded (token ghp_SECRET)"), GitHubRateLimitedError),
        (ToolExecutionError("GitHub API returned HTTP 500 for /repos/a/b"), GitHubUnavailableError),
        (ToolTimeoutError("get_github_repository", 20), GitHubUnavailableError),
        (MCPConnectionError("boom"), GitHubUnavailableError),
    ],
)
async def test_metadata_failures_abort_with_fixed_messages(db_session, error, expected):
    user, _, _ = seed(db_session)
    manager = FakeManager({"get_github_repository": error})
    with pytest.raises(expected) as info:
        await _evaluate(db_session, user, manager)
    assert "ghp_SECRET" not in info.value.message
    assert db_session.query(RepositoryEvaluation).count() == 0
    assert db_session.query(GithubRepository).count() == 0  # nothing persisted on failure


async def test_malformed_metadata_is_502(db_session):
    user, _, _ = seed(db_session)
    for bad in ({"unexpected": 1}, {"source": "live", "repository": {"name": 5}}):
        with pytest.raises(GitHubUnavailableError):
            await _evaluate(db_session, user, FakeManager({"get_github_repository": bad}))


async def test_github_mcp_server_missing_is_503(db_session):
    user, _, _ = seed(db_session)
    manager = FakeManager()
    manager._handlers = {}  # server not connected: no tool is discoverable
    with pytest.raises(GitHubMCPUnavailableError):
        await _evaluate(db_session, user, manager)


async def test_optional_failures_become_limitations(db_session):
    user, _, _ = seed(db_session)
    manager = FakeManager(
        {
            "get_repository_readme": ToolExecutionError("GitHub resource not found: /readme"),
            "get_repository_languages": {"languages_bytes": "not-a-dict"},
        }
    )
    result = await _evaluate(db_session, user, manager)
    assert any("README was not found" in lim for lim in result.limitations)
    assert any("languages could not be read" in lim for lim in result.limitations)
    assert result.signals["has_readme"] is False
    assert "python" not in _by_slug(result)  # no language data -> no language evidence
    assert "fastapi" in _by_slug(result)  # manifests still contribute


async def test_empty_repository(db_session):
    user, _, _ = seed(db_session)
    manager = FakeManager(
        {
            "get_repository_languages": {"languages_bytes": {}},
            "get_repository_structure": {"entries": [], "truncated": False},
            "get_repository_readme": ToolExecutionError("GitHub resource not found: /readme"),
        }
    )
    result = await _evaluate(db_session, user, manager)
    assert result.signals["empty_repository"] and result.evidence == []
    assert any("empty" in lim for lim in result.limitations)
    assert not any(name == "get_repository_file" for name, _ in manager.calls)  # no further inspection


async def test_unsupported_language_only_repo_yields_no_language_evidence(db_session):
    user, _, _ = seed(db_session)
    manager = FakeManager(
        {
            "get_repository_languages": {"languages_bytes": {"COBOL": 5000}},
            "get_repository_structure": {"entries": [{"path": "main.cob", "entry_type": "file"}], "truncated": False},
            "get_repository_readme": ToolExecutionError("GitHub resource not found: /readme"),
        }
    )
    result = await _evaluate(db_session, user, manager)
    assert result.evidence == [] and result.unrecognized_languages == ["COBOL"]
    assert any("COBOL" in lim for lim in result.limitations)


async def test_malformed_manifest_is_a_limitation(db_session):
    user, _, _ = seed(db_session)
    manager = FakeManager(
        {
            "get_repository_file": lambda a: (
                {"path": a["path"], "content": "not = [toml", "truncated": False}
                if a["path"] == "pyproject.toml"
                else {"path": a["path"], "content": "x", "truncated": False}
            )
        }
    )
    result = await _evaluate(db_session, user, manager)
    assert any("pyproject.toml could not be parsed" in lim for lim in result.limitations)
    assert "qdrant" not in _by_slug(result)


async def test_fork_and_archived_get_caveats(db_session):
    user, _, _ = seed(db_session)
    manager = FakeManager(
        {"get_github_repository": lambda a: details(f"{a['owner']}/{a['repo']}", is_fork=True, is_archived=True)}
    )
    result = await _evaluate(db_session, user, manager)
    assert any("fork" in lim for lim in result.limitations) and any("archived" in lim for lim in result.limitations)


async def test_tool_call_budget_is_bounded(db_session):
    user, _, _ = seed(db_session)
    entries = [{"path": f"requirements{i}.txt", "entry_type": "file"} for i in range(30)]
    manager = FakeManager(
        {
            "get_repository_structure": {
                "entries": [*entries, {"path": ".github", "entry_type": "dir"}],
                "truncated": True,
            }
        }
    )
    result = await _evaluate(db_session, user, manager)
    assert len(manager.calls) <= MAX_TOOL_CALLS
    assert any("truncated" in lim for lim in result.limitations)


async def test_only_allow_listed_arguments_are_sent(db_session):
    user, _, _ = seed(db_session)
    manager = FakeManager()
    await _evaluate(db_session, user, manager)
    paths = [a["path"] for name, a in manager.calls if name == "get_repository_file"]
    assert set(paths) <= {"pyproject.toml", "Dockerfile", ".github/workflows/ci.yml"}
    assert all(set(a) <= {"owner", "repo", "path"} for _, a in manager.calls)


async def test_evidence_survives_reload_and_cascades_on_user_delete(db_session):
    user, _, _ = seed(db_session)
    await _evaluate(db_session, user)
    db_session.expire_all()
    assert (
        db_session.query(SkillEvidence).count() == 7
    )  # python, fastapi x2 (manifest+README), qdrant, docker, ci-cd, rag
    db_session.delete(user)
    db_session.commit()
    assert db_session.query(SkillEvidence).count() == 0
    assert db_session.query(RepositoryEvaluation).count() == 0
