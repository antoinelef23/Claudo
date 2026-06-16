from webhooks.signing import sign


def test_sign_returns_hex_string():
    result = sign("mysecret", "{}")
    assert isinstance(result, str)
    assert all(c in "0123456789abcdef" for c in result)
    assert len(result) == 64


def test_sign_deterministic():
    sig1 = sign("mysecret", "{}")
    sig2 = sign("mysecret", "{}")
    assert sig1 == sig2


def test_sign_known_vector_spec_ex1():
    # HMAC-SHA256(secret="k", payload="{}") — valeur de référence spec EX-1
    expected = "add853b103fbcc936a194f9eb15e29c4ff08af6e47d5d1bca4f20218e31e4fff"
    assert sign("k", "{}") == expected


def test_sign_known_vector_2():
    # HMAC-SHA256(secret="mysecret", payload='{"key":"value"}')
    expected = "eec7f1700cc1636c63d5f3d21e9cce5f5114b789bdfb7ce53468d155d8f2f9ba"
    assert sign("mysecret", '{"key":"value"}') == expected


def test_sign_output_length_is_64_chars():
    assert len(sign("any_secret", "any_payload")) == 64


def test_sign_different_secrets_produce_different_signatures():
    assert sign("secret1", "{}") != sign("secret2", "{}")


def test_sign_different_payloads_produce_different_signatures():
    assert sign("k", "{}") != sign("k", '{"a":"b"}')


def test_sign_empty_payload_is_deterministic():
    assert sign("k", "") == sign("k", "")


def test_sign_empty_secret_is_deterministic():
    assert sign("", "payload") == sign("", "payload")
