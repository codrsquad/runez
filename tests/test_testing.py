import runez


def stringify(args):
    return str(args)


def crash(args):
    raise Exception("crashed: %s" % args)


def test_success():
    runez.testing.expect_success(stringify, "--dryrun {msg}", "hello", msg="hello")
    runez.testing.expect_failure(crash, "{msg}", "hello", "!foo", msg="hello")
