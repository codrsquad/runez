from mock import patch

import runez


def test_json(temp_base):
    assert runez.read_json(None) is None
    assert runez.save_json(None, None) == 0

    data = {"a": "b"}

    with runez.CaptureOutput(dryrun=True) as logged:
        assert runez.save_json(data, "sample.json") == 1
        assert "Would save" in logged.pop()

    with runez.CaptureOutput() as logged:
        assert runez.read_json("sample.json", fatal=False) is None
        assert "No file" in logged.pop()

        assert runez.read_json("sample.json", default={}, fatal=False) == {}
        assert not logged

        with patch("runez.open", side_effect=Exception):
            assert runez.save_json(data, "sample.json") == -1
            assert "Couldn't save" in logged.pop()

        assert runez.save_json(data, "sample.json", quiet=False) == 1
        assert "Saved " in logged.pop()

        with patch("io.open", side_effect=Exception):
            assert runez.read_json("sample.json", fatal=False) is None
            assert "Couldn't read" in logged.pop()

        assert runez.read_json("sample.json", quiet=False) == data
        assert "Read " in logged.pop()

        assert runez.read_json("sample.json", default=[]) == []
        assert "Wrong type" in logged.pop()

    with runez.CaptureOutput() as logged:
        # Try with an object that isn't directly serializable, but has a to_dict() function
        obj = runez.State()
        obj.to_dict = lambda *_: data

        assert runez.save_json(obj, "sample2.json", quiet=False) == 1
        assert "Saved " in logged.pop()

        assert runez.read_json("sample2.json", quiet=False) == data
        assert "Read " in logged.pop()
