import sys
import time

import pytest

import runez


@pytest.mark.skipif(sys.version_info[:2] < (3, 7), reason="Available in 3.7+")
def test_importtime():
    """Verify that importing runez remains fast"""
    check_importtime_within(3, "os")
    check_importtime_within(3, "sys")


def get_importtime(module):
    output = runez.run(sys.executable, "-Ximporttime", "-c", "import %s" % module, fatal=False, include_error=True)
    assert output
    total = 0
    cumulative = None
    for line in output.splitlines():
        stime, cumulative, mod_name = line.split("|")
        mod_name = mod_name.strip()
        if module in mod_name:
            value = runez.to_int(stime.partition(":")[2])
            assert value is not None, line
            total += value

    cumulative = runez.to_int(cumulative)
    assert cumulative is not None
    return total, cumulative


def average_importtime(module, count):
    cumulative = 0
    started = time.time()
    for _ in range(count):
        _, c = get_importtime(module)
        cumulative += c

    return cumulative / count, time.time() - started


def check_importtime_within(max_factor, module_name, count=5):
    """Check that 'import runez' is less than 'max_factor' times slower than that of 'module_name'"""
    c, e = average_importtime(module_name, count)
    cr, er = average_importtime("runez", count)
    cumulative_factor = cr / c
    elapsed_factor = er / e
    assert cumulative_factor < max_factor
    assert elapsed_factor < max_factor
