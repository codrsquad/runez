from runez.serialize import read_json, save_json
from runez.system import _R, resolved_path, stringified, SYS_INFO, UNSET


def ask_once(name, instructions, serializer=stringified, default=UNSET, logger=None, base="~/.config"):
    """
    Args:
        name (str): Name under which to store provided answer (will be stored in ~/.config/<name>.json)
        instructions (str): Instructions to show to user when prompt is necessary
        serializer (callable): Function that will turn provided value into object to be stored
        default: Default value to return if answer not available
        logger (callable | bool | None): Logger to use, True to print(), False to trace(), None to disable log chatter
        base (str): Base folder where to stored provided answer

    Returns:
        Value given by user (or 'default' if given), optionally wrapped via `serializer`
    """
    path = resolved_path(name, base=base)
    if not path.endswith(".json"):
        path += ".json"

    existing = read_json(path, default=None, logger=logger)
    if existing is not None:
        return existing

    if not SYS_INFO.terminal.is_stdout_tty:
        return _R.hdef(default, logger, "Can't prompt for %s, not on a tty" % name)

    try:
        provided = interactive_prompt(instructions)
        if provided:
            value = serializer(provided)
            if value is not None and save_json(value, path, fatal=False) >= 0:
                return value

            return _R.hdef(default, logger, "Invalid value provided for %s" % name)

        return _R.hdef(default, logger, "No value provided for %s" % name)

    except KeyboardInterrupt:
        return _R.hdef(default, logger, "Cancelled by user")


def interactive_prompt(message):
    try:
        compatible_input = raw_input

    except NameError:
        compatible_input = input

    return compatible_input(message)
