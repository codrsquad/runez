from pathlib import Path

import pytest

import runez
from runez.http import GlobalHttpCalls, RestClient, RestResponse, urljoin


EXAMPLE = RestClient("https://example.com")


@GlobalHttpCalls.allowed
def test_decorator_allowed():
    assert GlobalHttpCalls.is_forbidden() is False


@GlobalHttpCalls.forbidden
def test_decorator_forbidden():
    assert GlobalHttpCalls.is_forbidden() is True


@EXAMPLE.mock({
    "test/README.txt": "Hello",
})
def test_download(temp_folder, logged):
    r = EXAMPLE.put("test/README.txt", data=Path("foo"), fatal=False, dryrun=True)
    assert r.ok
    assert r.json() == {"message": "dryrun PUT https://example.com/test/README.txt"}
    assert "Would PUT" in logged.pop()

    with pytest.raises(FileNotFoundError):
        # fatal=False addresses http(s) communications only, not existence of files that are referred to by caller
        EXAMPLE.put("test/README.txt", data=Path("foo"), fatal=False, dryrun=False)
    assert not logged

    assert EXAMPLE.download("test/test.zip", "test.zip", dryrun=True).ok
    assert "Would download" in logged.pop()

    assert EXAMPLE.download("foo/test.zip", "test.zip", fatal=False).status_code == 404
    assert "404" in logged.pop()

    assert EXAMPLE.download("test/README.txt", "README.txt", fatal=False).ok
    assert "GET https://example.com/test/README.txt [200]" in logged.pop()
    assert runez.readlines("README.txt") == ["Hello"]

    EXAMPLE.untar("foo/test.tar.gz", "my-folder", dryrun=True)
    assert "Would untar test.tar.gz -> my-folder" in logged.pop()


def test_edge_cases():
    assert urljoin("", "") == ""
    assert urljoin("a", "") == "a"
    assert urljoin("", "b") == "b"
    assert urljoin("a", "b") == "a/b"
    assert urljoin("a#fragment", "b") == "a#fragment/b"
    assert urljoin("http://example.net/a", "b") == "http://example.net/a/b"
    assert urljoin("http://example.net/a", "https://example.com/b") == "https://example.com/b"
    assert urljoin("http://example.net/a/#/b", "https://example.com/b") == "https://example.com/b"
    assert urljoin("http://example.net/a/#/b", "c") == 'http://example.net/a/#/b/c'
    assert urljoin("http://example.net/a#b", "c") == 'http://example.net/a#b/c'

    r1 = RestResponse("GET", "http://foo", 400, '""')
    assert str(r1) == '400 ""'
    assert r1.description() == 'GET http://foo [400] ""'

    # Check message shortened (don't dump full output)
    r1 = RestResponse("GET", "http://foo", 400, "-" * 1050)
    desc = r1.description()
    assert len(desc) == 1027
    assert desc.endswith("...")


@EXAMPLE.mock({
    "README": "hello",
})
def test_files(temp_folder):
    # Exercise download code path
    sample = Path("README.txt")
    EXAMPLE.download("README", sample)
    assert runez.readlines(sample) == ["hello"]

    # Use local README.txt, which should get opened/closed appropriately
    # Exercise data=Path(...) code path, headers are temporarily used
    r = EXAMPLE.post("README", headers={"foo": "bar"}, data=sample)
    assert isinstance(r, RestResponse)
    assert r.ok

    # Exercise filepaths= code path
    r = EXAMPLE.post("README", filepaths={"sample": sample})
    assert isinstance(r, RestResponse)
    assert r.ok


def test_outgoing_disabled():
    assert GlobalHttpCalls.is_forbidden() is True
    with GlobalHttpCalls(True) as mg:
        assert GlobalHttpCalls.is_forbidden() is False
        assert str(mg) == "allowed"

    with GlobalHttpCalls(False) as mg:
        assert GlobalHttpCalls.is_forbidden() is True
        assert str(mg) == "forbidden"
        with pytest.raises(AssertionError) as exc:
            client = RestClient()
            client.head("https://example.com")
        assert "intentionally forbidden" in str(exc)

    assert GlobalHttpCalls.is_forbidden() is True


def test_reporting():
    # Verify reasonable extraction of error messages
    assert RestResponse.extract_message(None) is None
    assert RestResponse.extract_message(" foo ") == "foo"
    assert RestResponse.extract_message({"message": " oops "}) == "oops"
    assert RestResponse.extract_message({"error": " oops "}) == "oops"
    assert RestResponse.extract_message({"errors": " oops "}) == "oops"
    assert RestResponse.extract_message({"errors": [{"error": " nested "}]}) == "nested"


def dynamic_call(method, url):
    if url.endswith("-a"):
        return 201, "invalid json"  # Simulate request not return valid json

    return ["bar", method]  # Implied status 200


@EXAMPLE.mock({
    "foo-bar": {"foo": "bar"},  # status 200 implied, payload is a dict
    "bad-request": (400, dict(error="oops", msg="more info")),  # status 400, with sample error
    "server-crashed": (500, "failed"),  # status 500, with optional content as well
    "dynamic-a": dynamic_call,  # status and payload will come from function call
    "dynamic-b": dynamic_call,
    "explicit": RestResponse("", "", 202, "explicit RestResponse"),
    "fail1": Exception,
    "fail2": Exception("oops"),
})
def test_rest(logged):
    session = RestClient("https://example.com", headers={"test": "testing"})
    assert len(session.headers) == 2
    assert session.headers["test"] == "testing"
    assert session.headers["User-Agent"]

    assert session.url_exists("foo-bar") is True
    assert session.delete("foo-bar").ok
    assert "DELETE https://example.com/foo-bar [200]" in logged.pop()

    assert session.get("foo-bar") == {"foo": "bar"}
    assert session.get("https://example.com/foo-bar") == {"foo": "bar"}
    assert "GET https://example.com/foo-bar [200]" in logged.pop()
    assert session.post("foo-bar").ok
    assert "POST https://example.com/foo-bar [200]" in logged.pop()
    assert session.put("foo-bar").ok
    assert "PUT https://example.com/foo-bar [200]" in logged.pop()

    assert not session.post("bad-request", fatal=False).ok
    assert "POST https://example.com/bad-request [400] oops" in logged.pop()

    # Status 500 in mock spec does NOT impact dryrun
    assert session.post("server-crashed", dryrun=True).ok
    assert "Would POST" in logged.pop()

    # But does impact actual (no dryrun) run
    with pytest.raises(runez.system.AbortException):
        session.get("server-crashed", fatal=True)
    assert "GET https://example.com/server-crashed [500]" in logged.pop()
    r = session.get_response("server-crashed", fatal=False, logger=None)
    assert not r.ok
    assert r.status_code == 500

    assert session.url_exists("") is False
    assert session.url_exists("not-found") is False
    assert session.get("not-found", fatal=False, logger=None) is None
    assert session.head("not-found", fatal=False, logger=None).status_code == 404

    assert str(session.get_response("dynamic-a", logger=None)) == "201 invalid json"
    assert session.get("dynamic-b", logger=None) == ["bar", "GET"]
    assert not logged

    r = session.put("explicit")
    assert r.method == "PUT"
    assert str(r) == "202 explicit RestResponse"

    with pytest.raises(Exception) as exc:
        session.get("fail1")
    assert "Simulated crash" in str(exc)

    with pytest.raises(Exception) as exc:
        session.get("fail2")
    assert "oops" in str(exc)
