"""In-memory mock authentication backend (AC1).

NOTE: This is an in-memory mock for testing/prototyping only.
It is NOT production-grade authentication. No persistence, no network,
no filesystem, no database. All state lives in module-level dicts
cleared by reset_store().
"""

import hashlib
import hmac
import os
import uuid

# --- Storage layer (module-level state) -------------------------------------

# username -> User record: {'username': str, 'salt': bytes, 'password_hash': bytes}
_users: dict = {}

# project_id -> Project record: {'id': str, 'owner': str, 'name': str}
_projects: dict = {}

# username -> list[project_id]
_user_projects: dict = {}


# --- Crypto / password layer -----------------------------------------------

_PBKDF2_ITERATIONS = 100_000
_SALT_BYTES = 16
_HASH_NAME = 'sha256'


def _hash_password(password: str) -> tuple:
    """Return (salt, password_hash) for the given plaintext password."""
    salt = os.urandom(_SALT_BYTES)
    password_hash = hashlib.pbkdf2_hmac(
        _HASH_NAME,
        password.encode('utf-8'),
        salt,
        _PBKDF2_ITERATIONS,
    )
    return salt, password_hash


def _verify_password(password: str, salt: bytes, expected_hash: bytes) -> bool:
    """Constant-time comparison of a candidate password against stored hash."""
    candidate = hashlib.pbkdf2_hmac(
        _HASH_NAME,
        password.encode('utf-8'),
        salt,
        _PBKDF2_ITERATIONS,
    )
    return hmac.compare_digest(candidate, expected_hash)


# --- Public API layer -------------------------------------------------------

def reset_store() -> None:
    """Clear all in-memory state. Use for test isolation."""
    _users.clear()
    _projects.clear()
    _user_projects.clear()


# Interface stubs (full implementation in IMPLEMENTATION phase):

def signup(username: str, password: str) -> dict:
    """Register a new user and return a copy of the User record.

    Design contract (see DESIGN.md §2.1):
      - Returns: {'username': str, 'salt': bytes, 'password_hash': bytes}
      - Raises ValueError on: empty/whitespace username, empty/whitespace
        password, duplicate username.
      - Password is hashed via pbkdf2_hmac; plaintext is never stored.
      - Initializes _user_projects[username] = [].
    """
    if not isinstance(username, str) or not isinstance(password, str):
        raise ValueError('username and password must be strings')
    if not username or not username.strip():
        raise ValueError('username must not be empty or whitespace')
    if not password or not password.strip():
        raise ValueError('password must not be empty or whitespace')
    if username in _users:
        raise ValueError('username already exists')
    salt, password_hash = _hash_password(password)
    user = {'username': username, 'salt': salt, 'password_hash': password_hash}
    _users[username] = user
    _user_projects[username] = []
    return user.copy()


def login(username: str, password: str) -> dict:
    """Authenticate a user and return a copy of the User record.

    Design contract (see DESIGN.md §2.2):
      - Empty/whitespace checks run BEFORE the existence check (no enumeration).
      - Raises ValueError on: empty/whitespace username or password,
        unknown username, wrong password.
      - Password verified with hmac.compare_digest (constant-time).
    """
    if not isinstance(username, str) or not isinstance(password, str):
        raise ValueError('username and password must be strings')
    if not username or not username.strip():
        raise ValueError('username must not be empty or whitespace')
    if not password or not password.strip():
        raise ValueError('password must not be empty or whitespace')
    if username not in _users:
        raise ValueError('unknown username')
    user = _users[username]
    if not _verify_password(password, user['salt'], user['password_hash']):
        raise ValueError('wrong password')
    return user.copy()


def create_project(owner: str, name: str) -> dict:
    """Create a project under an existing owner and return a copy of it.

    Design contract (see DESIGN.md §2.3):
      - Returns: {'id': str(uuid4), 'owner': str, 'name': str}
      - Raises ValueError if owner is not a registered user or name is empty.
      - Appends the new pid to _user_projects[owner].
    """
    if owner not in _users:
        raise ValueError('owner is not a registered user')
    if not name or not name.strip():
        raise ValueError('project name must not be empty')
    pid = str(uuid.uuid4())
    project = {'id': pid, 'owner': owner, 'name': name}
    _projects[pid] = project
    _user_projects[owner].append(pid)
    return project.copy()


def list_projects(owner: str) -> list:
    """Return copies of all projects owned by `owner`, in creation order.

    Design contract (see DESIGN.md §2.4):
      - Returns [] for an unknown owner (does NOT raise) so the isolation
        query stays side-effect-free.
      - Only projects whose owner == `owner` are reachable (isolation).
    """
    return [_projects[pid].copy() for pid in _user_projects.get(owner, [])]