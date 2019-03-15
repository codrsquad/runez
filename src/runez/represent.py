def header(text, border="--"):
    """
    Args:
        text (str | unicode): Text to turn into a header
        border (str | unicode): Characters to use to decorate header

    Returns:
        (str): Decorated
    """
    if not text or not border:
        return text

    if border.endswith(" "):
        decorated = "%s%s" % (border, text)
        fmt = "{decorated}\n{hr}"

    else:
        decorated = "%s %s %s" % (border, text, border)
        fmt = "{hr}\n{decorated}\n{hr}"

    return fmt.format(decorated=decorated, hr=border[0] * len(decorated))
