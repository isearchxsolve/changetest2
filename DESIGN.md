# Design - In-Memory Mock Auth Backend (AC1)

> NOTE: This is an in-memory mock for testing/prototyping only. It is NOT production-grade authentication. No persistence, no network, no filesystem, no database.

This document specifies the detailed design derived from PLAN.md and ARCHITECTURE.md. It is backend-only (no UI/UX surface); the "design" here covers the data model, API contract, error catalog, and test matrix.

## 1. Data Model Design

### 1.1 User record (dict)
```python
{
    "username": str,       # unique key, non-empty, non-whitespace
    "salt": bytes,         # 16 bytes from os.urandom
    "password_hash": bytes # 32 bytes from pbkdf2_hmac('sha256', ...)
}
```
- Stored in `_users[username]`.
- **Never** contains a plaintext `password` field.
- Public functions return a **shallow copy** so callers cannot mutate internal state.

### 1.2 Project record (dict)
```python
{
    "id": str,     # str(uuid.uuid4())
    "owner": str,  # must be a signed-up username
    "name": str,   # non-empty
}
```
- Stored in `_projects[id]`.
- Owner's pid list: `_user_projects[owner]` (ordered append).

### 1.3 Module-level state
| Name | Type | Purpose |
|------|------|--------|
| `_users` | `dict[str, dict]` | username -> User record |
| `_projects` | `dict[str, dict]` | project_id -> Project record |
| `_user_projects` | `dict[str, list[str]]` | username -> ordered pids |

## 2. API Contract Design

### 2.1 `signup(username: str, password: str) -> dict`
**Returns:** copy of the new User record.
**Raises ValueError** (with messages) when:
| Condition | Message |
|-----------|--------|
| `username` is None / not a str | "username and password must be strings" |
| `username.strip() == ''` | "username must not be empty or whitespace" |
| `password` is None / not a str | "username and password must be strings" |
| `password.strip() == ''` | "password must not be empty or whitespace" |
| `username in _users` | "username already exists" |

**Side effects:** inserts into `_users`, initializes `_user_projects[username] = []`.

### 2.2 `login(username: str, password: str) -> dict`
**Returns:** copy of the matching User record.
**Raises ValueError** when:
| Condition | Message |
|-----------|--------|
| `username.strip() == ''` | "username must not be empty or whitespace" |
| `password.strip() == ''` | "password must not be empty or whitespace" |
| `username not in _users` | "unknown username" |
| password verify fails | "wrong password" |

Note: empty/whitespace checks run **before** the existence check so we never leak which usernames exist via empty-input probes.

### 2.3 `create_project(owner: str, name: str) -> dict`
**Returns:** copy of the new Project record.
**Raises ValueError** when:
| Condition | Message |
|-----------|--------|
| `owner not in _users` | "owner is not a registered user" |
| `name is None` / `name.strip() == ''` | "project name must not be empty" |

**Side effects:** mints `pid = str(uuid.uuid4())`, stores `_projects[pid]`, appends to `_user_projects[owner]`.

### 2.4 `list_projects(owner: str) -> list[dict]`
**Returns:** list of Project record copies for `owner`, in creation order. Empty list if owner has no projects (or is unknown — returns `[]`, does **not** raise, to keep the isolation query side-effect-free).

### 2.5 `reset_store() -> None`
Clears `_users`, `_projects`, `_user_projects`. Idempotent.

## 3. Crypto Design
- Algorithm: `hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100_000)`.
- Salt: `os.urandom(16)` — fresh per signup.
- Verify: re-derive with stored salt, compare via `hmac.compare_digest` (constant-time).
- Determinism note: identical inputs produce **equivalent** auth outcomes (login succeeds/fails consistently) even though salts differ per signup — required by NFR.

## 4. Test Matrix Design

14 tests, one behavior each. `autouse` function-scoped fixture calls `reset_store()` before+after each test.

| # | Test | Asserts |
|---|------|--------|
| 1 | `test_signup_returns_user_with_correct_username` | returned dict `username == 'alice'` |
| 2 | `test_signup_duplicate_username_raises` | 2nd signup raises ValueError; original user untouched |
| 3 | `test_signup_empty_username_raises` | `signup('', 'pw')` raises |
| 4 | `test_signup_empty_password_raises` | `signup('bob', '')` raises |
| 5 | `test_signup_whitespace_only_raises` | `signup('   ', '  ')` raises |
| 6 | `test_login_correct_credentials_returns_user` | returned user `username == 'alice'` |
| 7 | `test_login_wrong_password_raises` | raises ValueError |
| 8 | `test_login_unknown_username_raises` | raises ValueError |
| 9 | `test_password_not_stored_in_plaintext` | raw `'supersecret-password-123'` not in any stored value/bytes repr |
| 10 | `test_create_project_returns_project_with_owner_and_name` | owner & name match |
| 11 | `test_create_project_unknown_owner_raises` | raises ValueError |
| 12 | `test_two_projects_same_owner_distinct_and_retrievable` | both in `list_projects`, ids differ |
| 13 | `test_project_isolation_between_owners` | owner B's list does not contain A's project |
| 14 | `test_full_integration_flow` | signup -> login -> create_project -> `project['owner'] == username` |

## 5. Design Decisions
1. **Dicts over dataclasses** — minimal, stdlib-only, easy to inspect in tests.
2. **Return copies** — prevents external mutation of internal state.
3. **Empty-check before existence-check** in login — avoids user-enumeration via empty inputs.
4. **`list_projects` returns `[]` for unknown owner** — keeps the isolation query pure; existence is enforced only at `create_project`.
5. **`autouse` fixture** — guarantees isolation even if a future test forgets to reset.
6. **No plaintext anywhere** — neither stored nor returned; test #9 inspects `_users` directly to prove it.

## 6. Non-Goals
- No persistence, no tokens, no sessions, no roles, no rate limiting.
- No UI — this is a pure backend module.
- No external dependencies beyond pytest (dev-only).

## 7. Validation Order (state machine)

To keep behavior deterministic and failures unambiguous, every public function validates inputs in a fixed order. The first failing check wins.

### signup
```
1. type(username) is str AND type(password) is str   -> else ValueError
2. username is truthy AND username.strip() != ''     -> else ValueError
3. password is truthy AND password.strip() != ''     -> else ValueError
4. username not in _users                            -> else ValueError (duplicate)
5. hash, store, return copy
```

### login
```
1. type(username) is str AND type(password) is str   -> else ValueError
2. username is truthy AND username.strip() != ''     -> else ValueError
3. password is truthy AND password.strip() != ''     -> else ValueError
4. username in _users                                 -> else ValueError (unknown)
5. _verify_password(...)                              -> else ValueError (wrong password)
6. return copy
```

### create_project
```
1. owner in _users                                    -> else ValueError (unknown owner)
2. name is truthy AND name.strip() != ''              -> else ValueError (empty name)
3. mint uuid4, store, append, return copy
```

Rationale: login checks emptiness **before** existence to avoid leaking which
usernames are registered through empty-input probes (no user enumeration).

## 8. Isolation Invariant

For all owners A != B and all projects p:
```
p in list_projects(A)  <=>  p['owner'] == A  <=>  p['id'] in _user_projects[A]
```
Consequences enforced by construction:
- `_user_projects[A]` only ever receives pids created via `create_project(A, ...)`.
- `list_projects(B)` reads only `_user_projects[B]`, so A's pids are unreachable.
- Returning copies means even a shared dict reference cannot leak across owners.

This invariant is directly asserted by tests #12 and #13.

## 9. Test Fixture & Isolation Design

```python
@pytest.fixture(autouse=True)
def _isolate_store():
    reset_store()        # before: clean slate
    yield                # test body runs here
    reset_store()        # after: no leakage to next test
```

- `autouse=True` + function scope → every test gets isolation for free, even
  if a future contributor forgets to call `reset_store()`.
- Reset runs **before and after** so a test that crashes mid-way still leaves
  a clean store for the next one.
- Tests import only from `backend.auth_mock` — no reimplementation, no direct
  mutation of `_users`/`_projects`/`_user_projects` (test #9 only *reads* them
  to assert the no-plaintext invariant).
- Plain `assert` + `pytest.raises(ValueError)` — no custom assertion helpers,
  keeping failure messages unambiguous and stack traces short.

## 10. Requirements Traceability

| PLAN.md requirement | Design section | Test(s) |
|---------------------|----------------|---------|
| signup returns user, raises on dup/empty/whitespace | §2.1, §7 | #1–#5 |
| login returns user, raises on unknown/wrong/empty | §2.2, §7 | #6–#8 |
| pbkdf2_hmac, 16-byte salt, 100k iters, no plaintext | §3, §1.1 | #9 |
| create_project returns Project, raises on bad owner/empty name | §2.3, §7 | #10–#11 |
| Project isolation between owners | §8 | #12–#13 |
| reset_store clears state | §2.5, §9 | fixture (all) |
| Full integration flow | §2.1–§2.3 | #14 |
| stdlib + pytest only, in-memory, deterministic | §3, §6 | (structural) |
| Module + test docstrings (mock disclaimer) | §1 header | (structural) |
