import sys


print(".".join(str(s) for s in sys.version_info[:3]))
print(sys.prefix)
print(getattr(sys, "real_prefix", None) or getattr(sys, "base_prefix", sys.prefix))
