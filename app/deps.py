from uuid import UUID

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.security import decode_access_token

http_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(http_bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is not None:
        if credentials.scheme.lower() != "bearer":
            raise HTTPException(
                status_code=401,
                detail="Not authenticated",
                headers={"WWW-Authenticate": "Bearer"},
            )
        payload = decode_access_token(credentials.credentials)
        user_id = UUID(payload["sub"])
        user = db.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=401, detail="User not found")
        return user

    uid = request.session.get("user_id")
    if uid is not None:
        user = db.get(User, UUID(str(uid)))
        if user is not None:
            return user

    raise HTTPException(
        status_code=401,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_superadmin(user: User = Depends(get_current_user)) -> User:
    if user.role != "superadmin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user
