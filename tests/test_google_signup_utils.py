import pytest

from google_signup_agent import parse_dob

def test_parse_dob_accepts_iso() -> None:
    dob = parse_dob("2000-12-31")
    assert dob.to_iso() == "2000-12-31"

def test_parse_dob_accepts_dmy_slash() -> None:
    dob = parse_dob("31/12/2000")
    assert dob.to_iso() == "2000-12-31"

def test_parse_dob_rejects_underage() -> None:

    with pytest.raises(ValueError):
        parse_dob("2020-01-01")

