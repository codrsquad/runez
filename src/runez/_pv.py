import sys


if len(sys.argv) == 2 and sys.argv[1] == "dump":
    for k in dir(sys):
        print("%s: %s" % (k, getattr(sys, k)))

print(".".join(str(s) for s in sys.version_info[:3]))
print(sys.prefix)
print(getattr(sys, "real_prefix", None) or getattr(sys, "base_prefix", sys.prefix))
