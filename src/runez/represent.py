#  -*- encoding: utf-8 -*-

from runez.base import Slotted, stringified
from runez.colors import ColorManager, uncolored
from runez.convert import flattened, to_int
from runez.file import terminal_width


def align_left(text, width, fill=""):
    """
    Args:
        text (str): Text to align left
        width (int): Width to align it to
        fill (str | None): Optional character to fill with

    Returns:
        (str): Left-aligned text
    """
    fmt = "{:%s<%s}" % (fill, width)
    return fmt.format(text)


def align_center(text, width, fill=""):
    """
    Args:
        text (str): Text to center
        width (int): Width to align it to
        fill (str | None): Optional character to fill with

    Returns:
        (str): Centered text
    """
    fmt = "{:%s^%s}" % (fill, width)
    return fmt.format(text)


def align_right(text, width, fill=""):
    """
    Args:
        text (str): Text to align right
        width (int): Width to align it to
        fill (str | None): Optional character to fill with

    Returns:
        (str): Right-aligned text
    """
    fmt = "{:%s^%s}" % (fill, width)
    return fmt.format(text)


def aligner_by_name(name, default=align_left):
    """
    Args:
        name (str): Left, center or right

    Returns:
        (callable): Corresponding `align_()` function above
    """
    if name == "left":
        return align_left

    if name == "center":
        return align_center

    if name == "right":
        return align_right

    return default


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


def indented(text, indent=2):
    """
    Args:
        text: Text to indent
        indent (int): Number of spaces to indent with

    Returns:
        (str): All lines in `text` indented with `indent`
    """
    indent = " " * indent
    return "\n".join("%s%s" % (indent, line) for line in stringified(text).splitlines())


class PCell(object):
    text_width = 0
    text = None

    def __init__(self, column, value):
        """
        Args:
            column (PColumn):
            value:
        """
        self.column = column
        self.value = value
        column.add_cell(self)


class PColumn(object):
    def __init__(self, ptable, index):
        """
        Args:
            ptable (PTable):
            index (int):
        """
        self.ptable = ptable
        self.header_cell = ptable.header_cell(index)
        self.index = index
        self.text_width = 0
        self.allocated_width = 0
        self.cells = []

    def __repr__(self):
        w = self.text_width if self.text_width == self.allocated_width else "%s/%s" % (self.allocated_width, self.text_width)
        return "%s (%s), %s cells" % (self.index, w, len(self.cells))

    def add_cell(self, cell):
        self.cells.append(cell)
        cell.text = self.formatted(cell.value)
        cell.text_width = len(uncolored(cell.text))
        self.text_width = max(self.text_width, cell.text_width)
        self.allocated_width = self.text_width

    def formatted(self, value):
        return stringified(value)


class PChars(Slotted):
    __slots__ = ["first", "mid", "last", "h"]

    def _values_from_string(self, text):
        parts = list(text)
        missing = 4 - len(parts)
        if missing > 0:
            parts += [""] * missing

        first, mid, last, h = parts
        return dict(first=first, mid=mid, last=last, h=h)

    def __repr__(self):
        return self.represented_values(delimiter="", separator="", include_none=False, name_formatter=lambda x: "")


class PBorder(Slotted):
    # top, mid, bottom, cell, header, header-cell
    __slots__ = ["t", "m", "b", "c", "h", "hc", "pad"]

    def __repr__(self):
        return self.represented_values(delimiter=",", separator=":", include_none=False)

    def set_pad(self, value):
        self.pad = to_int(value)

    def _get_defaults(self):
        return dict(c=PChars(), pad=1)

    def _values_from_string(self, text):
        values = {}
        for part in text.split(","):
            value = PrettyTable.borders.get(part)
            if value:
                v = self._values_from_positional(value)
                if v:
                    values.update(v)

            else:
                key, _, value = part.partition(":")
                values[key] = value

        return values

    def _set_field(self, name, value):
        if value is not None and name != "pad":
            value = PChars.cast(value)

        super(PBorder, self)._set_field(name, value)


class PTable(object):
    def __init__(self, parent):
        """
        Args:
            parent (PrettyTable):
        """
        self.parent = parent
        self.padding = " " * parent.border.pad
        self.column_count = self._determine_columnt_count()
        self.default_cell = PHeaderCell(align=parent.align, style=parent.style, width=parent.width)
        self.rows = []
        self.columns = [PColumn(self, i) for i in range(self.column_count)]
        self.header_cells = []
        if parent.header.cells:
            for i, cell in enumerate(parent.header.cells):
                self.header_cells.append(PCell(self.columns[i], cell.text))

        for row in parent.rows:
            self.add_row(row)

        allocated_width = self.allocated_width
        available_width = parent.width or terminal_width(default=160)
        excess = available_width - allocated_width
        if excess < 0:
            adjustable = sorted((c for c in self.columns if c.header_cell.is_width_adjustable), key=lambda x: -x.text_width)
            assert adjustable

    @property
    def allocated_width(self):
        total = 0
        for column in self.columns:
            total += column.allocated_width

        return total

    def header_cell(self, index):
        cells = self.parent.header.cells
        if cells and index < len(cells):
            return cells[index]

        return self.default_cell

    def _determine_columnt_count(self):
        result = len(self.parent.header.cells or [])
        for row in self.parent.rows:
            result = max(result, len(row))

        return result

    def add_row(self, data):
        row = [None] * self.column_count
        for i, value in enumerate(data):
            row[i] = PCell(self.columns[i], value)

        self.rows.append(row)

    def get_string(self):
        result = []
        border = self.parent.border
        header = self.parent.header
        cb = border.t
        if header.cells:
            result.append(self.decorated_text(border.pad, cb))
            cb = border.h or border.t
            result.append(self.decorated_text(border.pad, border.hc or border.c, cells=self.header_cells))

        for row in self.rows:
            result.append(self.decorated_text(border.pad, cb))
            cb = border.m
            result.append(self.decorated_text(border.pad, border.c, cells=row))

        result.append(self.decorated_text(border.pad, border.b))
        return "\n".join(s for s in result if s)

    def decorated_text(self, pad, chars, cells=None):
        if not chars:
            return None

        result = []
        for column in self.columns:
            size = column.allocated_width
            if column.index == 0:
                if chars.first:
                    result.append(chars.first)

            elif chars.mid:
                result.append(chars.mid)

            if cells is None:
                size += 2 * pad
                if size and chars.h:
                    result.append(chars.h * size)

            else:
                cell_text = cells[column.index].text
                if cell_text:
                    size += len(cell_text) - len(uncolored(cell_text))

                cell_text = column.header_cell.align(cell_text, size)
                result.append("%s%s%s" % (self.padding, cell_text, self.padding))

        if chars.last:
            result.append(chars.last)

        if result:
            return "".join(result)


class PHeaderCell(Slotted):
    __slots__ = ["align", "style", "text", "show", "width"]

    @property
    def is_width_adjustable(self):
        return self.width is None or self.width <= 0

    def set_align(self, align):
        if not callable(align):
            align = aligner_by_name(align)

        self.align = align

    def _values_from_string(self, text):
        return dict(text=text)

    def _values_from_object(self, obj):
        return dict(text=stringified(obj))

    def _get_defaults(self):
        return dict(align=align_left, show=True)


class PHeader(Slotted):
    __slots__ = ["cells", "show"]

    def _values_from_string(self, text):
        return dict(cells=[PHeaderCell(t) for t in flattened(text, split=",")])

    def _values_from_object(self, obj):
        if isinstance(obj, int):
            return dict(cells=[PHeaderCell() for _ in range(obj)])

        if hasattr(obj, "__iter__"):
            return dict(cells=[PHeaderCell(x) for x in obj])

    def _get_defaults(self):
        return dict(show=True)


class PrettyTable(object):
    borders = dict(
        ascii="rstgrid,t:+++=,m:+++-",
        compact="c:   ,h:   -",
        dashed=u"t:┌┬┐┄,m:├┼┤┄,b:└┴┘┄,c:┆┆┆,h:┝┿┥━",
        dots="t:....,b::::.,c::::,h:.:..",
        empty="",
        framed=u"t:┍┯┑━,m:┝┿┥━,b:┕┷┙━,c:│││,h:╞╪╡═",
        github="h:-|--,c:|||",
        jira=dict(c="|||", hc=PChars(first="||", mid="||", last="||")),
        mysql="t:+++-,b:+++-,c:|||",
        reddit="h:-|--,c: | ",
        rst="t:  ==,b:  ==,c:  ",
        rstgrid="mysql,h:+++=",
    )

    def __init__(self, header=None, align=None, border=None, missing="-", style=None, width=None):
        """
        Args:
            header (list | str | int | None): Header to use, or column count
            align (str | callable | None): How to align cells by default (callable must accept 2 args: text and width)
            border (str | PBorder | None): How to represent missing cells (`None` or not provided)
            missing (str): How to represent missing cells (`None` or not provided)
            style (str | runez.colors.Renderable | None): Desired default style
            width (int | None): Desired width (defaults to detected terminal width)
        """
        self.header = PHeader.cast(header)
        self.border = PBorder.cast(border)
        self.missing = missing
        if not callable(align):
            align = aligner_by_name(align)

        self.align = align
        self.style = ColorManager.style.find_renderable(style)
        self.width = width
        self.rows = []

    def __str__(self):
        return self.get_string()

    def add_row(self, *row):
        """Add one row, accepts any kind of list/tuple"""
        self.rows.append(flattened(row))

    def add_rows(self, *rows):
        """Add multiple row at once"""
        for row in rows:
            self.add_row(row)

    def get_string(self):
        ptable = PTable(self)
        return ptable.get_string()
