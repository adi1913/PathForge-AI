from app.models.skill import Skill
from app.resume.skill_normalizer import SkillNormalizer


def _seed_skill(db, slug, name):
    skill = Skill(slug=slug, name=name)
    db.add(skill)
    db.commit()
    return skill


def test_case_insensitive_match(db_session):
    _seed_skill(db_session, "pytorch", "PyTorch")
    normalizer = SkillNormalizer(db_session)
    assert normalizer.normalize("pytorch").slug == "pytorch"
    assert normalizer.normalize("PYTORCH").slug == "pytorch"
    assert normalizer.normalize("PyTorch").slug == "pytorch"


def test_synonym_mapping(db_session):
    _seed_skill(db_session, "machine-learning", "Machine Learning")
    normalizer = SkillNormalizer(db_session)
    assert normalizer.normalize("ML").slug == "machine-learning"
    assert normalizer.normalize("Machine Learning").slug == "machine-learning"


def test_unmatched_skill_returns_none_and_does_not_insert(db_session):
    normalizer = SkillNormalizer(db_session)
    result = normalizer.normalize("SomeMadeUpTechnology")
    assert result is None
    assert db_session.query(Skill).filter_by(slug="somemadeuptechnology").count() == 0
    assert db_session.query(Skill).count() == 0  # nothing was inserted anywhere


def test_slugified_direct_match(db_session):
    _seed_skill(db_session, "rest-api", "REST API")
    normalizer = SkillNormalizer(db_session)
    assert normalizer.normalize("REST API").slug == "rest-api"
