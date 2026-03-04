# This script is used to inspect python binary installations, it needs to work adhoc (std lib only)
import json
import platform
import sys


def simple_inspection():
    if hasattr(sys, "_is_gil_enabled"):
        freethreading = not sys._is_gil_enabled()
    else:
        freethreading = False
    return {"version": ".".join(str(s) for s in sys.version_info[:3]), "machine": platform.machine(), "freethreading": freethreading}


if __name__ == "__main__":
    if len(sys.argv) == 1:
        print(json.dumps(simple_inspection()))
