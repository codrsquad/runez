# This script is used to inspect python binary installations, it needs to work adhoc (std lib only)
import json
import platform
import sys


def simple_inspection():
    return {"version": ".".join(str(s) for s in sys.version_info[:3]), "machine": platform.machine()}


if __name__ == "__main__":
    if len(sys.argv) == 1:
        print(json.dumps(simple_inspection()))
