import json
import os

from runez.system import abort, is_tty


def ask_once(name, instructions, serializer=str, fatal=True, base="~/.config", default=None):
    """
    Args:
        name (str): Name under which to store provided answer (will be stored in ~/.config/<name>.json)
        instructions (str): Instructions to show to user when prompt is necessary
        serializer (callable): Function that will turn provided value into object to be stored
        fatal (bool | None): Abort execution on failure if True
        base (str): Base folder where to stored provided answer
        default: Default value to return if answer not available

    Returns:
        Value given by user, optionally wrapped via `serializer`
    """
    path = os.path.join(base, name)
    path = os.path.expanduser(path)
    if not path.endswith(".json"):
        path += ".json"

    try:
        with open(path) as fh:
            return json.load(fh)

    except IOError:
        pass

    reason = "can't ask for value, not on a tty"
    if is_tty():
        try:
            reason = "no value provided"
            provided = interactive_prompt(instructions)
            if provided:
                value = serializer(provided)
                if value is not None:
                    with open(path, "wt") as fh:
                        json.dump(value, fh, sort_keys=True, indent=2)
                        fh.write("\n")

                    return value

                reason = "invalid value provided"

        except KeyboardInterrupt:
            reason = "cancelled by user"

    return abort("%s" % reason, fatal=(fatal, default))


def interactive_prompt(message):
    try:
        compatible_input = raw_input

    except NameError:
        compatible_input = input

    return compatible_input(message)
