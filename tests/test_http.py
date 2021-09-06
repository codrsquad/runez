from pathlib import Path

import pytest

import runez
from runez.http import GlobalHttpCalls, MockResponse, RestClient, RestHandler, RestResponse, urljoin


EXAMPLE = RestClient("https://example.com")


@GlobalHttpCalls.allowed
def test_decorator_allowed():
    assert GlobalHttpCalls.is_forbidden() is False
    with GlobalHttpCalls(allowed=False) as mg:
        assert GlobalHttpCalls.is_forbidden() is True
        assert str(mg) == "forbidden"

    assert GlobalHttpCalls.is_forbidden() is False


def test_default_disabled():
    assert GlobalHttpCalls.is_forbidden() is True
    with pytest.raises(AssertionError) as exc:
        client = RestClient()
        client.head("https://example.com")
    assert "intentionally forbidden" in str(exc)


@GlobalHttpCalls.forbidden
def test_decorator_forbidden():
    assert GlobalHttpCalls.is_forbidden() is True
    with GlobalHttpCalls(allowed=True) as mg:
        assert GlobalHttpCalls.is_forbidden() is False
        assert str(mg) == "allowed"

    assert GlobalHttpCalls.is_forbidden() is True


@EXAMPLE.mock({
    "test/README.txt": "Hello",
    "test/README.txt#sha256=a123": "Hello",
    "test/README.txt#sha256=185f8db32271fe25f561a6fc938b2e264306ec304eda518007d1764826381969": "Hello",
})
def test_download(temp_folder, logged):
    assert str(EXAMPLE) == "https://example.com"
    client = EXAMPLE.sub_client("test/")
    assert str(client) == "https://example.com/test/"
    r = client.put("README.txt", data=Path("foo"), fatal=False, dryrun=True)
    assert r.ok
    assert r.json() == {"message": "dryrun PUT https://example.com/test/README.txt"}
    assert "Would PUT" in logged.pop()

    with pytest.raises(FileNotFoundError):
        # fatal=False addresses http(s) communications only, not existence of files that are referred to by caller
        client.put("README.txt", data=Path("foo"), fatal=False, dryrun=False)
    assert not logged

    assert client.download("test.zip", "test.zip", dryrun=True).ok
    assert "Would download" in logged.pop()

    assert client.download("foo/test.zip", "test.zip", fatal=False).status_code == 404
    assert "404" in logged.pop()

    assert client.download("README.txt", "README.txt", fatal=False).ok
    assert "GET https://example.com/test/README.txt [200]" in logged.pop()
    assert runez.readlines("README.txt") == ["Hello"]

    # With checksum validation
    assert client.download("README.txt#sha256=a123", "README.txt", fatal=False) is None
    assert "Deleted README.txt" in logged
    assert "sha256 differs for README.txt: expecting a123, got " in logged.pop()

    r = client.download("README.txt#sha256=185f8db32271fe25f561a6fc938b2e264306ec304eda518007d1764826381969", "README.txt", fatal=False)
    assert r.ok

    client.decompress("foo/test.tar.gz", "my-folder", dryrun=True)
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

    with pytest.raises(Exception) as exc:
        RestClient(handler=RestHandler)
    assert "is not usable" in str(exc)


@EXAMPLE.mock({})
@RestClient.handler.mock
@EXAMPLE.mock
@RestClient.handler.mock({})
def test_files(temp_folder):
    """yolo"""
    # Exercise download code path
    sample = Path("README.txt")
    r = EXAMPLE.download("README", sample, fatal=False)
    assert r.status_code == 404
    assert r.url == "https://example.com/README"

    with EXAMPLE.mock({"README": "hello"}) as mm:
        assert str(mm) == "tests.test_http.test_files started, 1 specs"
        assert str(mm.stack) == "RequestsHandler mock active, 1 specs [depth: 5]"
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


@EXAMPLE.mock
@RestClient.handler.mock("https://example.com/tt", {"test": 205})
def test_handler_mock(logged):
    session = RestClient("https://example.com", handler=EXAMPLE.handler)
    assert session.head("tt/test", fatal=False).status_code == 205
    assert session.head("foo", fatal=False).status_code == 404

    with EXAMPLE.mock({"foo": 201, "tt/test": 206}) as mm:
        mock_stack = mm.stack
        assert str(mm.stack) == "RequestsHandler mock active, 2 specs [depth: 3]"
        assert str(mm) == "tests.test_http.test_handler_mock started, 2 specs"
        assert session.head("foo", fatal=False).status_code == 201
        assert session.head("tt/test", fatal=False).status_code == 206  # Comes from closest mock context

    assert str(mm) == "tests.test_http.test_handler_mock stopped, 2 specs"
    assert mm.stack is None
    assert str(mock_stack) == "RequestsHandler mock active, 1 specs [depth: 2]"
    assert session.head("foo", fatal=False).status_code == 404
    assert session.head("tt/test", fatal=False).status_code == 205  # Reverts back to prev mock


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
    "explicit": MockResponse(202, "explicit RestResponse"),
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

    assert session.purge("foo-bar").ok
    assert "PURGE https://example.com/foo-bar [200]" in logged.pop()

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

    assert str(session.get_response("dynamic-a", logger=None)) == "<Response [201]>"
    r = session.get_response("dynamic-b", logger=None)
    assert r.description(size=12) == "GET https://..."
    assert not logged

    r = session.put("explicit")
    assert r.method == "PUT"
    assert str(r) == "<Response [202]>"

    with pytest.raises(Exception) as exc:
        session.get("fail1")
    assert "Simulated crash" in str(exc)

    with pytest.raises(Exception) as exc:
        session.get("fail2")
    assert "oops" in str(exc)
