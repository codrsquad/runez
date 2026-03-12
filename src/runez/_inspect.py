# This script is used to inspect python binary installations, it needs to work adhoc (std lib only)
import json
import platform
import sys
import sysconfig


def simple_inspection():
    freethreading = sysconfig.get_config_var("Py_GIL_DISABLED")
    return {"version": ".".join(str(s) for s in sys.version_info[:3]), "machine": platform.machine(), "freethreading": freethreading}


if __name__ == "__main__":
    if len(sys.argv) == 1:
        print(json.dumps(simple_inspection()))
