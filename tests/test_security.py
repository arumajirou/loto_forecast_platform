import pytest

from loto.security import authenticate, parse_tokens, require_role


def test_token_auth_and_roles():
    tokens = parse_tokens("secret=alice:operator,review=bob:approver")
    alice = authenticate("secret", tokens)
    require_role(alice, "researcher")
    with pytest.raises(PermissionError):
        require_role(alice, "approver")
    with pytest.raises(PermissionError):
        authenticate("bad", tokens)
