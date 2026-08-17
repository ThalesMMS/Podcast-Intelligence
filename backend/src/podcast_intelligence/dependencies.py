from __future__ import annotations

import uuid
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from podcast_intelligence.config import Settings, get_settings
from podcast_intelligence.database import get_session
from podcast_intelligence.models import Membership, User
from podcast_intelligence.services.bootstrap import DEV_USER_ID
from podcast_intelligence.services.providers import ProviderRegistry, build_registry

bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True, slots=True)
class AuthContext:
    user_id: uuid.UUID
    workspace_id: uuid.UUID
    subject: str
    claims: dict[str, object]


@lru_cache(maxsize=1)
def get_registry() -> ProviderRegistry:
    return build_registry(get_settings())


@lru_cache(maxsize=1)
def _jwks_client(url: str) -> PyJWKClient:
    return PyJWKClient(url, cache_keys=True)


def get_auth_context(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthContext:
    if settings.auth_mode == "dev":
        return AuthContext(
            user_id=DEV_USER_ID,
            workspace_id=uuid.UUID(settings.default_workspace_id),
            subject="development-user",
            claims={"mode": "development"},
        )
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token required",
        )
    try:
        signing_key = _jwks_client(str(settings.oidc_jwks_url)).get_signing_key_from_jwt(
            credentials.credentials
        )
        claims = jwt.decode(
            credentials.credentials,
            signing_key.key,
            algorithms=["RS256", "ES256", "EdDSA"],
            audience=settings.oidc_audience,
            issuer=settings.oidc_issuer,
        )
        subject = str(claims["sub"])
        workspace_id = uuid.UUID(str(claims[settings.oidc_workspace_claim]))
    except (KeyError, ValueError, jwt.PyJWTError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid identity token",
        ) from exc

    user = session.scalar(select(User).where(User.external_subject == subject))
    if user is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is not provisioned")
    membership = session.scalar(
        select(Membership).where(
            Membership.workspace_id == workspace_id,
            Membership.user_id == user.id,
        )
    )
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is not a member of the requested workspace",
        )
    return AuthContext(
        user_id=user.id,
        workspace_id=workspace_id,
        subject=subject,
        claims=dict(claims),
    )


SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
RegistryDep = Annotated[ProviderRegistry, Depends(get_registry)]
AuthDep = Annotated[AuthContext, Depends(get_auth_context)]
