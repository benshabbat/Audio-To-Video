from web.routes import _valid_job_id


def test_accepts_alnum_and_hyphen():
    assert _valid_job_id("abc123-DEF-456") is True


def test_rejects_path_traversal_attempt():
    assert _valid_job_id("../../etc/passwd") is False


def test_rejects_special_characters():
    assert _valid_job_id("abc/def") is False
    assert _valid_job_id("abc.def") is False
