from types import SimpleNamespace
from convertvault.security import hash_password, token_pair, verify_password

def test_password_hash_is_not_plaintext():
    hashed = hash_password("a sufficiently long password")
    assert hashed != "a sufficiently long password"
    assert verify_password("a sufficiently long password", hashed)
    assert not verify_password("wrong password", hashed)

def test_access_and_refresh_tokens_are_distinct():
    user = SimpleNamespace(id="user-id", role=SimpleNamespace(value="user"))
    access, refresh = token_pair(user)
    assert access != refresh

