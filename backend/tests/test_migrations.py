from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from tests.conftest import BACKEND

EXPECTED_TABLES = {
    "users",
    "dance_projects",
    "reference_videos",
    "dance_segments",
    "reference_pose_frames",
    "practice_sessions",
    "user_pose_frames",
    "performance_scores",
    "feedback_items",
    "analysis_jobs",
}


def _cfg(url: str) -> Config:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def test_upgrade_creates_spec_tables_and_downgrade_is_clean(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'm.db'}"
    command.upgrade(_cfg(url), "head")
    engine = create_engine(url)
    assert EXPECTED_TABLES <= set(inspect(engine).get_table_names())
    command.downgrade(_cfg(url), "base")
    assert set(inspect(engine).get_table_names()) <= {"alembic_version"}


def test_models_match_migrations(tmp_path: Path) -> None:
    """Autogenerate must find nothing to do: ORM models and migrations agree."""
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    from app.db.base import Base

    url = f"sqlite:///{tmp_path / 'm.db'}"
    command.upgrade(_cfg(url), "head")
    with create_engine(url).connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == []


def test_project_delete_cascades(tmp_path: Path) -> None:
    from sqlalchemy.orm import Session

    from app.db.session import make_engine
    from app.models import AnalysisJob, DanceProject, DanceSegment, ReferenceVideo, User

    url = f"sqlite:///{tmp_path / 'm.db'}"
    command.upgrade(_cfg(url), "head")
    engine = make_engine(url)
    with Session(engine) as db:
        user = User(auth_provider="local", auth_provider_id="x")
        db.add(user)
        db.flush()
        project = DanceProject(owner_id=user.id, title="t")
        db.add(project)
        db.flush()
        db.add(
            ReferenceVideo(
                project_id=project.id,
                source_object_key="k",
                duration=1,
                source_fps=24,
                width=640,
                height=480,
            )
        )
        db.add(DanceSegment(project_id=project.id, position=0, start_time=0, end_time=1, title="s"))
        db.add(
            AnalysisJob(
                owner_id=user.id, project_id=project.id, kind="reference", idempotency_key="j1"
            )
        )
        db.commit()
        db.execute(text("DELETE FROM dance_projects"))
        db.commit()
        for table in ("reference_videos", "dance_segments", "analysis_jobs"):
            assert db.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar() == 0  # noqa: S608
