from runez.serialize import read_json, save_json
from runez.system import _R, resolved_path, stringified, SYS_INFO


def ask_once(name, instructions, default=None, base="~/.config", serializer=stringified, fatal=False, logger=False):
    """
    Args:
        name (str): Name under which to store provided answer (will be stored in ~/.config/<name>.json)
        instructions (str): Instructions to show to user when prompt is necessary
        default: Default value to return if answer not available
        base (str): Base folder where to stored provided answer
        serializer (callable): Function that will turn provided value into object to be stored
        logger (callable | bool | None): Logger to use, True to print(), False to trace(), None to disable log chatter
        fatal (type | bool | None): True: abort execution on failure, False: don't abort but log, None: don't abort, don't log

    Returns:
        Value given by user (or 'default' if given), optionally wrapped via `serializer`
    """
    path = resolved_path(name, base=base)
    if not path.endswith(".json"):
        path += ".json"

    existing = read_json(path, logger=logger)
    if existing is not None:
        return existing

    if not SYS_INFO.terminal.is_stdout_tty:
        return _R.habort(default, fatal, logger, "Can't prompt for %s, not on a tty" % name)

    try:
        provided = input(instructions)
        if provided:
            value = serializer(provided)
            if value is not None:
                save_json(value, path, fatal=fatal, logger=logger)
                return value

            return _R.habort(default, fatal, logger, "Invalid value provided for %s" % name)

        return _R.habort(default, fatal, logger, "No value provided for %s" % name)

    except KeyboardInterrupt:
        return _R.habort(default, fatal, logger, "Cancelled by user")
