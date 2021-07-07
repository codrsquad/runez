from pathlib import Path

import pytest

import runez
from runez.http import GlobalHttpCalls, mock_http, MockHttp, MockResponse, RestClient, urljoin


@GlobalHttpCalls.allowed
def test_decorator_allowed():
    assert GlobalHttpCalls.is_forbidden() is False


@GlobalHttpCalls.forbidden
def test_decorator_forbidden():
    assert GlobalHttpCalls.is_forbidden() is True


@mock_http({
    "https://example.com/test/README.txt": "Hello",
})
def test_download(temp_folder, logged):
    session = RestClient("https://example.com")

    r = session.put("test/README.txt", data=Path("foo"), fatal=False, dryrun=True)
    assert r.ok
    assert r.json() == {"message": "dryrun PUT https://example.com/test/README.txt"}
    assert "Would PUT" in logged.pop()

    with pytest.raises(FileNotFoundError):
        # fatal=False addresses http(s) communications only, not existence of files that are referred to by caller
        session.put("test/README.txt", data=Path("foo"), fatal=False, dryrun=False)
    assert not logged

    assert session.download("test/test.zip", "test.zip", dryrun=True).ok
    assert "Would download" in logged.pop()

    assert session.download("foo/test.zip", "test.zip", fatal=False).status_code == 404
    assert "404" in logged.pop()

    assert session.download("test/README.txt", "README.txt", fatal=False).ok
    assert "GET https://example.com/test/README.txt [200]" in logged.pop()
    assert runez.readlines("README.txt") == ["Hello"]

    session.untar("foo/test.tar.gz", "my-folder", dryrun=True)
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

    assert RestClient.response_description(None) == ""

    r1 = MockResponse("GET", "http://foo", '""', 400)
    assert str(r1) == '400 ""'
    r1.payload = "invalid json"
    assert RestClient.response_description(r1) == "GET http://foo [400 Bad request] invalid json"

    r1.history = [MockResponse("GET", "http://foo", "", 400)]
    s = RestClient.response_description(r1)
    assert "Response history" in s

    # Check message shortened (don't dump full output)
    r1 = MockResponse("GET", "http://foo", "-" * 1050, 400)
    assert RestClient.response_snippet(r1).endswith("...")


@mock_http({
    "_base": "https://example.com",
    "README": "hello",
})
def test_files(temp_folder):
    session = RestClient("https://example.com")
    assert len(session.headers) == 1

    # Exercise download code path
    sample = Path("README.txt")
    session.download("README", sample)
    assert runez.readlines(sample) == ["hello"]

    # Use local README.txt, which should get opened/closed appropriately
    # Exercise data=Path(...) code path, headers are temporarily used
    r = session.post("README", headers={"foo": "bar"}, data=sample)
    assert isinstance(r, MockResponse)
    assert r.ok
    assert len(r.kwargs) == 3
    assert "data" in r.kwargs

    # Exercise filepaths= code path
    r = session.post("README", filepaths={"sample": sample})
    assert isinstance(r, MockResponse)
    assert r.ok
    assert len(r.kwargs) == 3
    assert "sample" in r.kwargs["files"]


def test_new_session(monkeypatch):
    # Test replacing RestClient.new_session with a custom function
    class MySession:
        """Simulates a non-requests session... we're exercising .get() only here"""
        def __init__(self, app):
            self.app = app

        def get(self, url, **kwargs):
            return MockResponse("GET", url, {"app": self.app}, 201, **kwargs)

    def dedicated_session(app=None):
        return MySession(app)

    def my_session(client, app=None):
        """Simulate a custom session creator, with 'app' as custom session_spec"""
        assert isinstance(client, RestClient)
        assert client.base_url == "https://example.com"
        return MySession(app)

    session = RestClient("https://example.com", app="my-app", new_session=dedicated_session)
    r = session.get_response("foo")
    assert r.ok
    assert r.json() == {"app": "my-app"}

    monkeypatch.setattr(RestClient, "new_session", my_session)
    session = RestClient("https://example.com", app="my-app")
    r = session.get_response("foo")
    assert r.status_code == 201
    assert r.json() == {"app": "my-app"}

    r = session.get_response("foo")
    assert r.ok
    assert r.json() == {"app": "my-app"}


def test_outgoing_disabled():
    assert GlobalHttpCalls.is_forbidden() is True
    with GlobalHttpCalls(allowed=True) as mg:
        assert GlobalHttpCalls.is_forbidden() is False
        assert str(mg) == "allowed"

    with GlobalHttpCalls(allowed=False) as mg:
        assert GlobalHttpCalls.is_forbidden() is True
        assert str(mg) == "forbidden"
        with pytest.raises(AssertionError) as exc:
            client = RestClient()
            client.head("https://example.com")
        assert "intentionally forbidden" in str(exc)

    assert GlobalHttpCalls.is_forbidden() is True


def test_reporting():
    # Verify reasonable extraction of error messages
    assert RestClient.extract_message(None) is None
    assert RestClient.extract_message(" foo ") == "foo"
    assert RestClient.extract_message({"message": " oops "}) == "oops"
    assert RestClient.extract_message({"error": " oops "}) == "oops"
    assert RestClient.extract_message({"errors": " oops "}) == "oops"
    assert RestClient.extract_message({"errors": [{"error": " nested "}]}) == "nested"


def dynamic_call(method, url, **_):
    if url.endswith("-a"):
        return 201, "invalid json"  # Simulate request not return valid json

    if method == "POST":
        return None  # Simulate invalid mock-spec (should return an int, string, or payload)

    return ["bar"]  # Implied status 200


@mock_http({
    "_base": "https://example.com",  # Base url (so we don't have to repeat it on every line below)
    "foo-bar": {"foo": "bar"},  # status 200 implied, payload is a dict
    "bad-request": (400, dict(error="oops", msg="more info")),  # status 400, with sample error
    "server-crashed": (500, "failed"),  # status 500, with optional content as well
    "not-found": 404,  # status 404 (payload unimportant, will default to "status 404")
    "dynamic-a": dynamic_call,  # status and payload will come from function call
    "dynamic-b": dynamic_call,
}, default_status=405)
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

    # 'undeclared-spec' not present in mock_http() -> defaults to specified default_status
    assert session.head("undeclared-spec", fatal=False, logger=None).status_code == 405
    assert session.url_exists("undeclared-spec") is False
    assert session.url_exists("") is False

    assert not session.post("bad-request", fatal=False).ok
    assert "POST https://example.com/bad-request [400 Bad request] oops {" in logged.pop()

    # Status 500 in mock spec does NOT impact dryrun
    assert session.post("server-crashed", dryrun=True).ok
    assert "Would POST" in logged.pop()

    # But does impact actual (no dryrun) run
    with pytest.raises(runez.system.AbortException):
        session.get("server-crashed", fatal=True)
    assert "GET https://example.com/server-crashed [500 Internal error]" in logged.pop()
    r = session.get_response("server-crashed", fatal=False, logger=None)
    assert r.status_code == 500
    with pytest.raises(IOError) as exc:
        r.raise_for_status()
    assert "Internal error" in str(exc)

    with MockHttp({
        "_base": "https://example.com",
        "a": MockResponse("", "", "", 123),
        "fail1": Exception,
        "fail2": Exception("oops"),
    }) as ms:
        assert str(ms) == "3 specs"
        assert str(ms.specs.get("https://example.com/a")) == "https://example.com/a 123 "
        assert session.get_response("foo-bar", fatal=False).status_code == 404  # No access to parent mock...
        assert session.get_response("a", fatal=False).status_code == 123
        with pytest.raises(Exception):
            session.get_response("fail1", fatal=False)

        with pytest.raises(Exception):
            session.get_response("fail2", fatal=False)
        logged.pop()

    assert session.get("not-found", fatal=False, logger=None) is None
    assert session.head("not-found", fatal=False, logger=None).status_code == 404

    assert str(session.get_response("dynamic-a", logger=None)) == "201 invalid json"
    assert session.get("dynamic-b", logger=None) == ["bar"]
    assert not logged

    with pytest.raises(AssertionError) as exc:
        # dynamic_call() returns None for POST, which is interpreted as an invalid mock-spec
        session.post("dynamic-b", fatal=False)
    assert "Check mock response: None" in str(exc)
