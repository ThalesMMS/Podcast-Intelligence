from __future__ import annotations

import uuid

import typer

from podcast_intelligence.config import get_settings
from podcast_intelligence.database import SessionLocal, job_execution_session
from podcast_intelligence.services.bootstrap import bootstrap_infrastructure
from podcast_intelligence.services.pipeline import JobPipeline
from podcast_intelligence.services.providers import build_registry
from podcast_intelligence.services.seed import seed_demo

app = typer.Typer(help="Podcast Intelligence administrative CLI")


@app.command("bootstrap")
def bootstrap() -> None:
    """Create the development workspace and object-store bucket."""
    settings = get_settings()
    registry = build_registry(settings)
    try:
        with SessionLocal() as session:
            bootstrap_infrastructure(session, settings, registry)
    finally:
        registry.http.close()
    typer.echo("Infrastructure initialized")


@app.command("seed-demo")
def seed_demo_command() -> None:
    """Create an idempotent, fully indexed demonstration episode."""
    settings = get_settings()
    registry = build_registry(settings)
    try:
        with SessionLocal() as session:
            bootstrap_infrastructure(session, settings, registry)
            episode = seed_demo(session, settings)
    finally:
        registry.http.close()
    typer.echo(f"Demo episode ready: {episode.id}")


@app.command("process-job")
def process_job(job_id: uuid.UUID) -> None:
    """Run a job synchronously for diagnostics."""
    settings = get_settings()
    with job_execution_session(job_id) as session:
        if session is None:
            raise typer.BadParameter(f"Job {job_id} is already running")
        registry = build_registry(settings)
        try:
            JobPipeline(session, registry).run(job_id)
        finally:
            registry.http.close()
    typer.echo(f"Job {job_id} completed")


if __name__ == "__main__":
    app()
