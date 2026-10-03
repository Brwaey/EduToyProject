"""Per-account encrypted credentials. Never log or serialize secrets."""

import os

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select

from .db import now
from .models_ai import AIConfig
from .security import Problem


def cipher(settings, db, create=False):
    path = settings.ai_key_file
    if not path.exists():
        if not create or db.scalar(
            select(AIConfig.owner_id).where(AIConfig.encrypted_key.is_not(None)).limit(1)
        ):
            raise Problem(
                503, "ai_key_unavailable", "主密钥缺失，请恢复原主密钥文件；手动功能仍可使用"
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as file:
                file.write(Fernet.generate_key())
        except FileExistsError:
            pass
    try:
        return Fernet(path.read_bytes())
    except (ValueError, OSError):
        raise Problem(503, "ai_key_unavailable", "主密钥不可用，请检查密钥文件") from None


def decrypt(settings, db, config):
    if not config or not config.encrypted_key:
        raise Problem(409, "ai_not_configured", "请先填写模型设置")
    try:
        return cipher(settings, db).decrypt(config.encrypted_key.encode()).decode()
    except InvalidToken:
        raise Problem(503, "ai_key_unavailable", "主密钥与配置不匹配，请恢复原主密钥") from None


def config_view(settings, db, owner):
    c = db.get(AIConfig, owner)
    available = False
    if c and c.encrypted_key:
        try:
            decrypt(settings, db, c)
            available = True
        except Problem:
            pass
    return dict(
        version=c.version if c else 0,
        endpoint=c.endpoint if c else "",
        model=c.model if c else "",
        has_key=bool(c and c.encrypted_key),
        key_available=available,
        test_status=c.test_status if c else "untested",
    )


def save_config(settings, db, owner, value):
    c = db.get(AIConfig, owner)
    if (c.version if c else 0) != value.expected_version:
        raise Problem(409, "version_conflict", "模型配置已更新，请重新载入")
    if not value.api_key and (not c or not c.encrypted_key or c.endpoint != value.url):
        raise Problem(422, "ai_key_required", "首次配置或更换地址时请填写 API Key")
    encrypted = (
        cipher(settings, db, create=True).encrypt(value.api_key.encode()).decode()
        if value.api_key
        else c.encrypted_key
    )
    if not c:
        c = AIConfig(owner_id=owner, version=0)
        db.add(c)
    c.version += 1
    c.endpoint, c.model, c.encrypted_key = value.url, value.model, encrypted
    c.test_status, c.updated_at = "untested", now()
    db.flush()
    return config_view(settings, db, owner)
