# This script is used to inspect python binary installations, it needs to work adhoc (std lib only)
import json
import platform
import sys


def simple_inspection():
    return dict(
        version=".".join(str(s) for s in sys.version_info[:3]),
        machine=platform.machine(),
        sys_prefix=sys.prefix,
        base_prefix=getattr(sys, "base_prefix", sys.prefix),
    )


if __name__ == "__main__":
    if len(sys.argv) == 1:
        print(json.dumps(simple_inspection()))
