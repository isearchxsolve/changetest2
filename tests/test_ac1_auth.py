"""Tests for the in-memory mock auth backend (AC1).

NOTE: These tests target an in-memory mock, NOT production auth.
All imports come from backend.auth_mock; no logic is reimplemented here.
No network, filesystem, or database access is performed.
"""

import pytest

from backend import auth_mock
from backend.auth_mock import (
    create_project,
    list_projects,
    login,
    reset_store,
    signup,
)


@pytest.fixture(autouse=True)
def _clean_store():
    """Ensure every test starts from an empty store (order-independent)."""
    reset_store()
    yield
    reset_store()


# Each test asserts exactly ONE behavior so failures are unambiguous.

def test_signup_returns_user_with_correct_username():
    """#1: signup returns a user whose username matches the input."""
    user = signup('alice', 'secret123')
    assert user['username'] == 'alice'


def test_signup_duplicate_username_raises():
    """#2: duplicate signup raises ValueError; existing user untouched."""
    first = signup('alice', 'secret123')
    with pytest.raises(ValueError):
        signup('alice', 'different456')
    # Existing user must still log in with the ORIGINAL password.
    logged_in = login('alice', 'secret123')
    assert logged_in['username'] == 'alice'
    assert logged_in['salt'] == first['salt']
    assert logged_in['password_hash'] == first['password_hash']


def test_signup_empty_username_raises():
    """#3: signup('') raises ValueError."""
    with pytest.raises(ValueError):
        signup('', 'secret123')


def test_signup_empty_password_raises():
    """#4: signup with empty password raises ValueError."""
    with pytest.raises(ValueError):
        signup('alice', '')


def test_signup_whitespace_only_raises():
    """#5: signup with whitespace-only username/password raises ValueError."""
    with pytest.raises(ValueError):
        signup('   ', 'secret123')
    with pytest.raises(ValueError):
        signup('alice', '   ')
    with pytest.raises(ValueError):
        signup('\t\n', '\t\n')


def test_login_correct_credentials_returns_user():
    """#6: login with correct creds returns the matching user."""
    signup('alice', 'secret123')
    user = login('alice', 'secret123')
    assert user['username'] == 'alice'


def test_login_wrong_password_raises():
    """#7: login with wrong password raises ValueError."""
    signup('alice', 'secret123')
    with pytest.raises(ValueError):
        login('alice', 'wrongpass')


def test_login_unknown_username_raises():
    """#8: login with unknown username raises ValueError."""
    with pytest.raises(ValueError):
        login('nobody', 'secret123')


def test_password_not_stored_in_plaintext():
    """#9: raw password string is not present anywhere in the store."""
    password = 'supersecret-password-123'
    signup('alice', password)
    # Inspect the internal store directly.
    users = auth_mock._users
    projects = auth_mock._projects
    user_projects = auth_mock._user_projects
    # The raw password string must not appear in any stored value.
    for store in (users, projects, user_projects):
        for key, value in _iter_items(store):
            assert password not in _as_text(key)
            assert password not in _as_text(value)
    # And the stored user record must carry a non-empty salt + hash (bytes).
    record = users['alice']
    assert isinstance(record['salt'], (bytes, bytearray))
    assert isinstance(record['password_hash'], (bytes, bytearray))
    assert len(record['salt']) >= 16
    assert len(record['password_hash']) > 0


def test_create_project_returns_project_with_owner_and_name():
    """#10: create_project returns a Project with correct owner & name."""
    signup('alice', 'secret123')
    project = create_project('alice', 'My Project')
    assert project['owner'] == 'alice'
    assert project['name'] == 'My Project'
    assert isinstance(project['id'], str)
    assert len(project['id']) > 0


def test_create_project_unknown_owner_raises():
    """#11: create_project under an unregistered owner raises ValueError."""
    with pytest.raises(ValueError):
        create_project('ghost', 'Project X')


def test_two_projects_same_owner_distinct_and_retrievable():
    """#12: two projects under one owner are both retrievable, ids differ."""
    signup('alice', 'secret123')
    p1 = create_project('alice', 'Project One')
    p2 = create_project('alice', 'Project Two')
    assert p1['id'] != p2['id']
    owned = list_projects('alice')
    ids = {p['id'] for p in owned}
    assert ids == {p1['id'], p2['id']}
    names = {p['name'] for p in owned}
    assert names == {'Project One', 'Project Two'}


def test_project_isolation_between_owners():
    """#13: a project under owner A is not returned for owner B."""
    signup('alice', 'secret123')
    signup('bob', 'password456')
    create_project('alice', 'Alice Only')
    create_project('bob', 'Bob Only')
    alice_projects = list_projects('alice')
    bob_projects = list_projects('bob')
    assert len(alice_projects) == 1
    assert alice_projects[0]['name'] == 'Alice Only'
    assert alice_projects[0]['owner'] == 'alice'
    assert len(bob_projects) == 1
    assert bob_projects[0]['name'] == 'Bob Only'
    assert bob_projects[0]['owner'] == 'bob'
    # Cross-check: Bob's project id must not appear in Alice's list.
    assert bob_projects[0]['id'] not in {p['id'] for p in alice_projects}


def test_full_integration_flow():
    """#14: signup -> login -> create_project -> project.owner == username."""
    signup('alice', 'secret123')
    user = login('alice', 'secret123')
    project = create_project(user['username'], 'Integration Project')
    assert project['owner'] == user['username']
    assert project['owner'] == 'alice'
    # The project must be retrievable via list_projects for that owner.
    owned = list_projects('alice')
    assert any(p['id'] == project['id'] for p in owned)


# --- helpers ---------------------------------------------------------------

def _iter_items(store):
    """Yield (key, value) pairs for dict-like stores."""
    if hasattr(store, 'items'):
        yield from store.items()
    else:
        for i, v in enumerate(store):
            yield (i, v)


def _as_text(obj):
    """Best-effort flatten an object to a string for substring checks."""
    if obj is None:
        return ''
    if isinstance(obj, (bytes, bytearray)):
        # Decode bytes defensively; ignore undecodable bytes.
        try:
            return obj.decode('utf-8', errors='ignore')
        except Exception:
            return ''
    if isinstance(obj, str):
        return obj
    # Recurse into containers.
    parts = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            parts.append(_as_text(k))
            parts.append(_as_text(v))
    elif isinstance(obj, (list, tuple, set)):
        for v in obj:
            parts.append(_as_text(v))
    else:
        parts.append(str(obj))
    return ''.join(parts)
