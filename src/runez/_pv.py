import sys


def version_string():
    text = getattr(sys, "version", None) or "no-version"
    impl = getattr(sys, "implementation", None)
    if impl:
        impl = getattr(impl, "name", None)
        if impl:
            text += " %s" % impl

    return text.replace("\n", " ")


if len(sys.argv) == 2 and sys.argv[1] == "dump":  # pragma: no cover
    for k in dir(sys):
        print("%s: %s" % (k, getattr(sys, k)))

print(version_string())
print(sys.prefix)
print(getattr(sys, "base_prefix", sys.prefix))
