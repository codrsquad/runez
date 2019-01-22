from runez.testing import expect_failure, expect_success


def stringify(args):
    return str(args)


def crash(args):
    raise Exception("crashed: %s" % args)


def test_success():
    expect_success(stringify, "--dryrun {msg}", "hello", msg="hello")
    expect_failure(crash, "{msg}", "hello", "!foo", msg="hello")
