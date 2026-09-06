# Architecture - In-Memory Mock Auth Backend (AC1)

> NOTE: This is an in-memory mock for testing/prototyping only. It is NOT production-grade authentication. No persistence, no network, no filesystem, no database.

## Overview

A single-module Python stdlib implementation providing user signup, login, and project creation with strict per-owner project isolation. All state lives in module-level dictionaries cleared by `reset_store()`.

## Components

### 1. `backend/auth_mock.py` (Core Module)

The entire backend is a single module with three logical layers:

#### 1.1 Storage Layer (module-level state)
- `_users: dict[str, dict]` — maps `username` -> User record
- `_projects: dict[str, dict]` — maps `project_id` -> Project record
- `_user_projects: dict[str, list[str]]` — maps `username` -> ordered list of project_ids owned by that user
- `reset_store()` — clears all three dicts; the only mutation path for test isolation.

#### 1.2 Crypto / Password Layer
- `_hash_password(password: str) -> tuple[bytes, bytes]` — generates a 16-byte salt via `os.urandom`, derives `password_hash` via `hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100_000)`. Returns `(salt, password_hash)`.
- `_verify_password(password: str, salt: bytes, expected_hash: bytes) -> bool` — re-derives the hash with the stored salt and compares with `hmac.compare_digest`.
- Plaintext passwords are NEVER stored. Only `salt` (bytes) and `password_hash` (bytes) are persisted on the User record.

#### 1.3 Public API Layer
- `signup(username, password) -> dict` — validates inputs, rejects duplicates/empty/whitespace, hashes password, stores User, returns a copy of the User record (without plaintext).
- `login(username, password) -> dict` — validates inputs, looks up user, verifies password, returns the User record or raises `ValueError`.
- `create_project(owner, name) -> dict` — validates owner exists and name non-empty, mints a `uuid.uuid4()` id, stores Project, appends to `_user_projects[owner]`, returns the Project record.
- `list_projects(owner) -> list[dict]` — helper used by tests to assert isolation; returns only projects whose owner == `owner`.

### 2. `tests/test_ac1_auth.py` (Test Suite)
- Imports everything under test from `backend.auth_mock` (no reimplementation).
- `autouse` function-scoped fixture calls `reset_store()` before every test → order-independent, deterministic.
- 14 distinct test functions, each asserting exactly one behavior.
- Failure cases use `with pytest.raises(ValueError):`.

## Data Flow

### Signup Flow
```
Caller --signup(u, p)--> validate(u, p)
  |-> reject if u empty/whitespace -> ValueError
  |-> reject if p empty/whitespace -> ValueError
  |-> reject if u in _users      -> ValueError
  |-> _hash_password(p) -> (salt, hash)
  |-> _users[u] = {username, salt, password_hash}
  |-> _user_projects.setdefault(u, [])
  |-> return copy of User record
```

### Login Flow
```
Caller --login(u, p)--> validate(u, p)
  |-> reject if u empty/whitespace -> ValueError
  |-> reject if p empty/whitespace -> ValueError
  |-> reject if u not in _users   -> ValueError (unknown username)
  |-> _verify_password(p, salt, stored_hash)
  |-> reject if mismatch          -> ValueError (wrong password)
  |-> return copy of User record
```

### Create Project Flow
```
Caller --create_project(owner, name)--> validate
  |-> reject if owner not in _users -> ValueError
  |-> reject if name empty/whitespace -> ValueError
  |-> pid = str(uuid.uuid4())
  |-> project = {id: pid, owner, name}
  |-> _projects[pid] = project
  |-> _user_projects[owner].append(pid)
  |-> return copy of Project record
```

### Isolation Flow (query)
```
list_projects(owner)
  |-> [ _projects[pid] for pid in _user_projects.get(owner, []) ]
  |-> only projects whose owner == owner are reachable
  |-> other owners' pids never appear in _user_projects[owner]
```

### Reset Flow
```
reset_store()
  |-> _users.clear(); _projects.clear(); _user_projects.clear()
  |-> next test starts from empty state
```

## Tech Stack
- **Language:** Python 3.8+
- **Stdlib only:** `hashlib` (pbkdf2_hmac), `os` (urandom), `uuid` (uuid4), `hmac` (compare_digest)
- **Test runner:** `pytest` (the only non-stdlib dependency, dev-only)
- **No** network / filesystem / database / external services

## Interface Contracts (signatures)

```python
def signup(username: str, password: str) -> dict: ...
def login(username: str, password: str) -> dict: ...
def create_project(owner: str, name: str) -> dict: ...
def list_projects(owner: str) -> list: ...
def reset_store() -> None: ...
```

### Return shapes
- **User record:** `{'username': str, 'salt': bytes, 'password_hash': bytes}`
- **Project record:** `{'id': str, 'owner': str, 'name': str}`

### Error contract
- All validation failures raise `ValueError` with a descriptive message.
- No other exception types are raised by the public API.

## Module Dependency Graph

```
backend/__init__.py        (package marker)
    |
    +-- backend/auth_mock.py   (core: storage + crypto + public API)
            ^
            | imports (no reimplementation)
            |
tests/__init__.py         (package marker)
    |
    +-- tests/test_ac1_auth.py  (pytest suite, autouse reset_store fixture)
```

- No cross-module coupling beyond `tests -> backend.auth_mock`.
- No third-party imports at runtime; `pytest` is dev-only.
- The test module reads `auth_mock._users / _projects / _user_projects` only to
  assert the no-plaintext invariant and isolation — it never mutates them
  directly (all mutations go through the public API or `reset_store()`).

## Design Decisions
1. **Dicts over dataclasses** — keeps the mock minimal and stdlib-only; records are plain dicts.
2. **Return copies** — public functions return shallow copies so callers cannot mutate internal state directly.
3. **`hmac.compare_digest`** — constant-time comparison for password verification.
4. **`autouse` fixture** — guarantees isolation without every test remembering to call `reset_store()`.
5. **`list_projects` helper** — exposes the isolation contract for direct testing without leaking internals.
