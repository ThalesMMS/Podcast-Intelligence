from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from podcast_intelligence.config import Settings
from podcast_intelligence.models import Membership, User, Workspace
from podcast_intelligence.services.providers import ProviderRegistry

DEV_USER_SUBJECT = "development-user"
DEV_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")


def bootstrap_database(session: Session, settings: Settings) -> None:
    if settings.auth_mode != "dev":
        return

    workspace_id = uuid.UUID(settings.default_workspace_id)
    workspace = session.get(Workspace, workspace_id)
    if workspace is None:
        workspace = Workspace(id=workspace_id, name="Development Workspace", slug="development")
        session.add(workspace)

    user = session.scalar(select(User).where(User.external_subject == DEV_USER_SUBJECT))
    if user is None:
        user = User(
            id=DEV_USER_ID,
            external_subject=DEV_USER_SUBJECT,
            email="dev@localhost",
            display_name="Development User",
        )
        session.add(user)
    session.flush()

    membership = session.scalar(
        select(Membership).where(
            Membership.workspace_id == workspace_id,
            Membership.user_id == user.id,
        )
    )
    if membership is None:
        session.add(Membership(workspace_id=workspace_id, user_id=user.id, role="owner"))
    session.commit()


def bootstrap_infrastructure(
    session: Session, settings: Settings, registry: ProviderRegistry
) -> None:
    bootstrap_database(session, settings)
    registry.object_store.ensure_bucket()
