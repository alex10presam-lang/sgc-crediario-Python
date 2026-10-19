import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select

from sgc.models import LoginAttempt, User

ITERATIONS = 600_000


class DomainError(ValueError):
    """An operation the interface can explain without a traceback."""


@dataclass(frozen=True)
class Actor:
    user_id: int
    company: str
    auth_version: int = 1


def password_hash(password):
    if not 12 <= len(password) <= 256:
        raise DomainError("A senha deve ter entre 12 e 256 caracteres.")
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), ITERATIONS).hex()
    return f"pbkdf2_sha256${ITERATIONS}${salt}${digest}"


def verify_password(password, stored):
    if len(password) > 256:
        return False
    try:
        algorithm, iterations, salt, digest = stored.split("$")
        if algorithm != "pbkdf2_sha256" or int(iterations) != ITERATIONS:
            return False
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt), int(iterations)
        ).hex()
        return hmac.compare_digest(actual, digest)
    except (ValueError, TypeError, AttributeError):
        return False


def authorize(session, actor, roles=None):
    user = session.get(User, actor.user_id)
    if (
        not user
        or not user.active
        or user.company != actor.company
        or user.auth_version != actor.auth_version
    ):
        raise DomainError("Sua sessão não está disponível. Entre novamente.")
    if roles and user.role not in roles:
        raise DomainError("Seu perfil não pode realizar esta operação.")
    return user


def authenticate(database, company, username, password):
    company, username = company.strip().lower(), username.strip().lower()
    key = hashlib.sha256(f"{company}\0{username}".encode()).hexdigest()
    now = datetime.now()
    actor = None
    with database.transaction() as session:
        attempt = session.get(LoginAttempt, key)
        if attempt and attempt.locked_until and attempt.locked_until > now:
            raise DomainError("Aguarde um minuto antes de tentar novamente.")
        user = session.scalar(
            select(User).where(User.company == company, User.username == username)
        )
        valid = verify_password(password, user.password_hash) if user else False
        if valid and user.active:
            actor = Actor(user.id, user.company, user.auth_version)
            if attempt:
                session.delete(attempt)
        else:
            if not attempt:
                attempt = LoginAttempt(key=key, failures=0)
                session.add(attempt)
            if attempt.locked_until and attempt.locked_until <= now:
                attempt.failures = 0
                attempt.locked_until = None
            attempt.failures += 1
            if attempt.failures >= 5:
                attempt.locked_until = now + timedelta(minutes=1)
    if actor is None:
        raise DomainError("Empresa, usuário ou senha inválidos.")
    return actor
