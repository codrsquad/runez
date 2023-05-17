import sys


def sys_version():
    return ".".join(str(s) for s in sys.version_info[:3])


if __name__ == "__main__":
    if len(sys.argv) == 1:
        print(sys_version())
        print(sys.prefix)
        print(getattr(sys, "base_prefix", sys.prefix))
        sys.exit(0)
