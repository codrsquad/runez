def header(text, dash="-", width=2):
    """
    Args:
        text (str): Text to turn into a header
        dash (str): Character to use to decorate header
        width (int): Length

    Returns:
        (str): Decorated
    """
    if not text or not width:
        return text

    dashes = dash * abs(width)

    if width > 0:
        decorated = "%s %s %s" % (dashes, text, dashes)

    else:
        decorated = "%s %s" % (dashes, text)

    border = dash * len(decorated)

    if width > 0:
        return "%s\n%s\n%s" % (border, decorated, border)

    return "%s\n%s" % (decorated, border)
