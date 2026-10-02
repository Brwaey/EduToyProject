import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import Depends, Request, Response
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from .db import now
from .models import LoginSession, User

COOKIE = "yanji_session"
passwords = PasswordHash.recommended()


class Problem(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message


def db_session(request: Request):
    with request.app.state.sessions() as session:
        yield session


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass
class Identity:
    user: User
    session: LoginSession


def current_user(request: Request, db: Annotated[Session, Depends(db_session)]) -> Identity:
    token = request.cookies.get(COOKIE, "")
    session = db.get(LoginSession, token_hash(token)) if token else None
    if session is None or session.expires_at <= now():
        raise Problem(401, "unauthorized", "请登录后继续")
    user = db.get(User, session.user_id)
    if user is None:
        raise Problem(401, "unauthorized", "登录已失效")
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        supplied = request.headers.get("X-CSRF-Token", "")
        if not secrets.compare_digest(supplied, session.csrf_token):
            raise Problem(403, "csrf_failed", "会话校验失败，请刷新页面后重试")
    return Identity(user, session)


def issue_session(db: Session, user: User, response: Response, secure: bool) -> LoginSession:
    token = secrets.token_urlsafe(32)
    session = LoginSession(
        token_hash=token_hash(token),
        user_id=user.id,
        csrf_token=secrets.token_urlsafe(32),
        expires_at=(datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
    )
    db.add(session)
    response.set_cookie(
        COOKIE,
        token,
        max_age=7 * 86400,
        httponly=True,
        samesite="lax",
        secure=secure,
        path="/",
    )
    return session
