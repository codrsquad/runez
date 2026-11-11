# Todo

Ideas noticed while using runez elsewhere, to look at here.

## `RestClient.post()` and co: a 404 should probably return `None`

`RestClient.get()` returns the deserialized json, or `None` when the response isn't ok. But the
other verbs (`post()`, `put()`, ...) return the raw `RestResponse` and default to `fatal=True`.
A query-style POST that gets a 404 ("no such thing") therefore aborts. To get `None` for
"not found", the caller has to pass `fatal=False`, check `.ok`, then check `status_code != 404`
before aborting on real errors.

Seen in nfty's `deps` command (`src/nfty/deps/__init__.py`, `ServiceClient`). Astrid and pystrid
take query bodies via POST, and a 404 there means "not known" rather than an error. `ServiceClient`
wraps both verbs to get: json on success, `None` on 404, abort on anything else.

Things to decide:

- **Should every verb behave the same?** For example, a `.json()`-returning flavor of `post()`,
  `put()` and `delete()`.
- **Should `fatal=True` treat 404 as `None` rather than abort?** `get()` already returns `None`
  for a 404 when not fatal.

## `mock()`: allow a callable as catch-all spec

`MockedHandlerStack.response_for_url()` only looks up exact URLs in a dict, and `start()` copies
the given specs. So a test must know every URL, including its query string (e.g.
`...?page=1&size=1000`), before it runs. Being able to pass one function
`(method, url) -> response` as a fallback would let a test serve fixture files dynamically. nfty's
`tests/test_deps.py` would use it: it maps json files under `tests/deps/` to the URLs being
queried.
