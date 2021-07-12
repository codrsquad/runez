import os

from runez.colors import cast_style
from runez.convert import to_int
from runez.system import _R, AdaptedProperty, flattened, is_iterable, joined, short, Slotted, stringified
from runez.system import SYS_INFO, UNSET, wcswidth


NAMED_BORDERS = dict(
    ascii="rstgrid,t:+++=,m:+++-",
    compact="c:   ,h:   -",
    colon="c: : ,h: : -",
    dots="t:....,b::::.,c::::,h:.:..",
    empty="",
    framed="t:┍┯┑━,m:┝┿┥━,b:┕┷┙━,c:│││,h:╞╪╡═",
    github="h:-|--,c:|||",
    mysql="t:+++-,b:+++-,c:|||",
    reddit="h:-|--,c: | ",
    rst="t:  ==,b:  ==,c:  ",
    rstgrid="mysql,h:+++=",
)


class Align:
    """Text alignment functions, in a class for clean import and contextualized short names"""

    @staticmethod
    def left(text, width, fill=""):
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

    @staticmethod
    def center(text, width, fill=""):
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

    @staticmethod
    def right(text, width, fill=""):
        """
        Args:
            text (str): Text to align right
            width (int): Width to align it to
            fill (str | None): Optional character to fill with

        Returns:
            (str): Right-aligned text
        """
        fmt = "{:%s>%s}" % (fill, width)
        return fmt.format(text)

    @staticmethod
    def cast(name, default=UNSET):
        """
        Args:
            name (str | callable | None): Left, center or right
            default (str | callable | None): Default to use if 'name' doesn't refer to an existing aligner

        Returns:
            (callable): Corresponding function
        """
        if callable(name):
            return name

        if name:
            func = getattr(Align, name.lower(), None)
            if func:
                return func

        if default is None:
            return None

        if default is UNSET:
            raise ValueError("Invalid horizontal alignment '%s'" % name)

        if callable(default):
            return default

        func = getattr(Align, default.lower(), None)
        if func:
            return func

        raise ValueError("Invalid default horizontal alignment '%s'" % default)


class Header:
    """Simple textual header functions, in a class for clean import and contextualized short names"""

    @classmethod
    def aerated(cls, text, border="--"):
        """
        Args:
            text (str): Text to turn into a header
            border (str): Characters to use to decorate header

        Returns:
            (str): 'text' decorated with simple border
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


class PrettyBorder(Slotted):
    # top, mid, bottom, cell, header, header-cell
    __slots__ = ["t", "m", "b", "c", "h", "hc", "pad"]

    def __repr__(self):
        return self.represented_values(delimiter=",", operator=":")

    def set_pad(self, value):
        self.pad = to_int(value)

    def _get_defaults(self):
        return dict(c=_PTBorderChars(), pad=1)

    def _values_from_string(self, text):
        values = {}
        for part in text.split(","):
            value = NAMED_BORDERS.get(part)
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
            value = _PTBorderChars.cast(value)

        super()._set_field(name, value)


class PrettyCustomizable:
    """
    Ancestor to customizable points, in reverse order of priority
    - table: overall settings, acts as default for all cells
    - header: applies to header row only
    - header.column: applies to all cells within a column (including header cells)
    """

    align = AdaptedProperty("align", caster=Align.cast, doc="Horizontal alignment to use (left, center or right)")
    style = AdaptedProperty("style", caster=cast_style, doc="Style")
    width = AdaptedProperty("width", caster=int, doc="Desired width")

    def to_dict(self):
        result = {}
        for key in ("align", "style", "width"):
            value = getattr(self, key)
            if value is not None:
                result[key] = value

        return result

    def formatted(self, text):
        style = self.style
        if style is not None:
            text = style(text)

        return text

    @staticmethod
    def merged(*chain):
        values = dict(align=Align.left)
        for item in chain:
            if item is not None:
                values.update(item.to_dict())

        result = PrettyCustomizable()
        for k, v in values.items():
            setattr(result, k, v)

        return result


class PrettyColumn(PrettyCustomizable):
    def __init__(self, index, text=None):
        self.index = index
        self.text = None if text is None else stringified(text)
        self.shown = True

    def __repr__(self):
        cid = "[c%s]" % self.index
        if self.text is None:
            return cid

        return "%s '%s'" % (cid, self.text)


class PrettyHeader(PrettyCustomizable):
    def __init__(self, value=None):
        self._columns = []
        self.shown = True
        if value is None:
            return

        if isinstance(value, str):
            for t in flattened(value, split=","):
                self.add_column(t)

        elif isinstance(value, int):
            self.accommodate(value)

        elif hasattr(value, "__iter__"):
            for x in value:
                self.add_column(x)

        else:
            raise ValueError("Invalid header '%s'" % value)

    def __getitem__(self, identifier):
        """
        Args:
            identifier (str | int): Header title, or column index

        Returns:
            (PrettyColumn): Corresponding column
        """
        if isinstance(identifier, int):
            return self._columns[identifier]

        for c in self._columns:
            if identifier == c.text:
                return c

        raise KeyError("No header column '%s'" % identifier)

    def __len__(self):
        return len(self._columns)

    @property
    def columns(self):
        return self._columns

    @property
    def shown_columns(self):
        return [c for c in self._columns if c.shown]

    def hide(self, *ids):
        """Hide all columns with 'ids'"""
        for i in ids:
            self[i].shown = False

    def show(self, *ids):
        """Show all columns with 'ids'"""
        for i in ids:
            self[i].shown = True

    def accommodate(self, size):
        """
        Args:
            size (int): Ensure that we have at least 'size' columns
        """
        while len(self._columns) < size:
            self.add_column()

    def add_column(self, text=None):
        self._columns.append(PrettyColumn(len(self._columns), text))

    def add_columns(self, *columns):
        for c in columns:
            self.add_column(c)


class PrettyTable(PrettyCustomizable):

    border = AdaptedProperty("border", type=PrettyBorder, doc="Border to use")
    header = AdaptedProperty("header", type=PrettyHeader, doc="Header")

    def __init__(self, header=None, align=None, border=None, missing="-", style=None, width=None):
        """
        Args:
            header (PrettyHeader | str | int | list | dict | tuple | None): Header to use, or column count
            align (str | callable | None): How to align cells by default (callable must accept 2 args: text and width)
            border (PrettyBorder | str | None): What border to use
            missing (str): How to represent missing cells (`None` or not provided)
            style (str | runez.colors.Renderable | None): Desired default style (eg: dim, bold, etc)
            width (int | None): Desired width (defaults to detected terminal width)
        """
        self.header = header  # type: PrettyHeader
        self.align = align
        self.border = border
        self.missing = missing
        self.style = style
        self.width = width
        self._rows = []

    def __str__(self):
        return self.get_string()

    @property
    def rows(self):
        return self._rows

    def formatted(self, value):
        return stringified(value, none=self.missing)

    def add_row(self, *values):
        """Add one row with given 'values'"""
        row = flattened(values)
        self.header.accommodate(len(row))
        self._rows.append(row)

    def add_rows(self, *rows):
        """Add multiple rows at once"""
        for row in rows:
            self.add_row(row)

    def get_string(self):
        """Table rendered as a string"""
        t = _PTTable(self)
        result = t.get_string()
        return result

    @staticmethod
    def _single_diag(sources, border, align, style, missing, columns):
        table = PrettyTable(2, border=border)
        table.header[0].align = align
        table.header[1].style = style
        col1 = 0
        rows = []
        for source in sources:
            if callable(source):
                source = source()

            if isinstance(source, dict):
                source = sorted(source.items())

            elif not is_iterable(source):
                source = [source]

            for row in source:
                if not isinstance(row, (tuple, list)):
                    row = (row, "")

                row = [_represented_cell(s, missing) for s in row]
                col1 = max(col1, len(row[0]))
                rows.append(row)

        columns = max(columns - col1 - 5, 10)
        for row in rows:
            if len(row) == 2 and row[1]:
                row[1] = short(row[1], size=columns, uncolor=True)

            table.add_row(row)

        return table.get_string()

    @staticmethod
    def two_column_diagnostics(
        *sources, align="right", border=UNSET, columns=UNSET, delimiter="\n\n", missing=UNSET, style=UNSET, title_color=UNSET
    ):
        """
        Args:
            *sources (callable | iterable | dict): Must yield pairs of values (name of diagnostic, and its value)
            align (str): Alignment for 1st column (default: right)
            border (str): Border for the PrettyTable used to render the two-column diagnostics
            columns (int | None): Optional max number of columns in output (default: terminal width)
            delimiter (str): Delimiter to use between sub-diagnostics sections
            missing (callable | None): Color to use to represent missing values (default: orange)
            style (callable | None): Style for 2nd column (default: bold)
            title_color (callable | None): Color to use for titles of sub-diagnostics sections (default: blue)

        Returns:
            (PrettyTable): Rendered PrettyTable showing diagnostics info
        """
        border = _R.rdefault(border, os.environ.get("DIAGNOSTICS_BORDER") or "colon")
        columns = _R.rdefault(columns, SYS_INFO.terminal.columns)
        missing = _R.rdefault(missing, _R._runez_module().orange)
        style = _R.rdefault(style, _R._runez_module().bold)
        title_color = _R.rdefault(title_color, _R._runez_module().blue)
        additional = []
        named_sources = {}
        regular_sources = []
        for source in sources:
            if isinstance(source, dict):
                named_sources.update(source)

            elif isinstance(source, str):
                additional.append(source)

            else:
                regular_sources.append(source)

        report = []
        if regular_sources:
            report.append(PrettyTable._single_diag(regular_sources, border, align, style, missing, columns))

        for title, source in sorted(named_sources.items()):
            if title_color:
                title = title_color(title)

            if not isinstance(source, list):
                source = [source]

            content = PrettyTable._single_diag(source, border, align, style, missing, columns)
            content = "%s:\n%s" % (title, content)
            report.append(content)

        if additional:
            report.extend(additional)

        return joined(report, delimiter=delimiter)


def render_line(container, columns, padding, pad, chars, cells=None):
    if not chars:
        return

    result = []
    for index, column in enumerate(columns):
        size = column.allocated_width
        if index == 0:
            if chars.first:
                result.append(chars.first)

        elif chars.mid:
            result.append(chars.mid)

        if cells is None:
            size += 2 * pad
            if size and chars.h:
                result.append(chars.h * size)

        else:
            cell = cells[index]
            result.append(cell.rendered_text(size, padding))

    if chars.last:
        result.append(chars.last)

    if result:
        line = "".join(result)
        container.append(line.rstrip())


class _PTBorderChars(Slotted):
    __slots__ = ["first", "mid", "last", "h"]

    def _values_from_string(self, text):
        return self._values_from_object(list(text))

    def _values_from_object(self, obj):
        if isinstance(obj, list):
            missing = 4 - len(obj)
            if missing > 0:
                obj += [""] * missing

            first, mid, last, h = obj
            return dict(first=first, mid=mid, last=last, h=h)

        return super()._values_from_object(obj)

    def __repr__(self):
        return self.represented_values(delimiter="", operator="", name_formatter=lambda x: "")


class _PTTable:
    def __init__(self, parent):
        """
        Args:
            parent (PrettyTable): Table to take a snapshot of for rendering
        """
        self.parent = parent
        header = parent.header
        shown_columns = header.shown_columns
        self.columns = [_PTColumn(self, c) for c in shown_columns]
        self.column_count = len(self.columns)
        header_shown = header.shown and any(c.text for c in shown_columns)
        header_row = [c.text for c in parent.header.columns]
        self.header_row = self.new_row(header_row, header=header) if header_shown else None
        self.rows = [self.new_row(r) for r in parent.rows]

    def new_row(self, values, header=None):
        row = []
        nvalues = len(values)
        for column in self.columns:
            i = column.index
            value = values[i] if i < nvalues else None
            cell = _PTCell(column, value, header)
            row.append(cell)

        return row

    def get_string(self):
        container = []
        columns = self.columns
        border = self.parent.border
        pad = border.pad
        padding = " " * pad
        cb = border.t
        if self.header_row:
            render_line(container, columns, padding, pad, cb)
            cb = border.h or border.t
            render_line(container, columns, padding, pad, border.hc or border.c, cells=self.header_row)

        for row in self.rows:
            render_line(container, columns, padding, pad, cb)
            cb = border.m
            render_line(container, columns, padding, pad, border.c, cells=row)

        render_line(container, columns, padding, pad, border.b)
        return "\n".join(container)


class _PTColumn:
    def __init__(self, ptable, pcolumn):
        """
        Args:
            ptable (_PTTable):
            pcolumn (PrettyColumn):
        """
        self.ptable = ptable
        self.pcolumn = pcolumn
        self.text_width = 0
        self.allocated_width = 0

    def __repr__(self):  # pragma: no cover
        return "%s" % self.pcolumn

    @property
    def index(self):
        """Index in main table"""
        return self.pcolumn.index

    def update_width(self, width):
        self.text_width = max(self.text_width, width)
        self.allocated_width = self.text_width


class _PTCell:
    """Holds text and settings for a cell in the table"""

    def __init__(self, column, value, header):
        """
        parent customization_chain
        cell: column -> table
        header cell: column -> header -> table

        Args:
            column (_PTColumn): Associated column
            value: Value to be rendered
            header (PrettyHeader | None): Header, if cell is part of it
        """
        self.custom = PrettyCustomizable.merged(column.pcolumn, header, column.ptable.parent)
        self.column = column
        self.value = value
        text = column.ptable.parent.formatted(value)
        text = self.custom.formatted(text)
        self.text = text
        self.text_width = wcswidth(text)
        column.update_width(self.text_width)

    def rendered_text(self, size, padding):
        text = self.text
        if text:
            size += len(text) - wcswidth(text)

        text = self.custom.align(text, size)
        return "%s%s%s" % (padding, text, padding)


def _represented_cell(text, missing):
    if text is None:
        return missing("-missing-")

    if text is UNSET:
        return missing("UNSET")

    return stringified(text)
