# -*- coding: utf-8 -*-

# MIT License / Copyright (c) 2021 by Dave Vandenbout.

from functools import reduce
import logging
import os
import re
import shutil
import sys

USING_PYTHON2 = sys.version_info.major == 2
USING_PYTHON3 = not USING_PYTHON2

if USING_PYTHON2:
    reload(sys)
    sys.setdefaultencoding("utf8")
else:
    # Python3 doesn't have basestring, so create one.
    basestring = type("")


DEBUG_OVERVIEW = logging.DEBUG
DEBUG_DETAILED = logging.DEBUG - 1
DEBUG_OBSESSIVE = logging.DEBUG - 2


def sexp_indent(s, tab="    "):
    """Indent an S-expression string.

    Args:
        s (string): S-expression string.
        tab (string, optional): Indentation string. Defaults to "    ".

    Returns:
        string: Indented S-expression.
    """

    out_s = ""
    indent = ""
    nl = ""  # First '(' will not be preceded by a newline.
    in_quote = False
    backslash = False

    for c in s:
        if c == "(" and not in_quote:
            out_s += nl + indent
            nl = "\n"  # Every '(' from now on gets preceded by a newline.
            indent += tab
        elif c == ")" and not in_quote:
            indent = indent[len(tab) :]
        elif c == '"' and not backslash:
            in_quote = not in_quote

        if c == "\\":
            backslash = True
        else:
            backslash = False

        out_s += c

    return out_s


# def find_by_key(key, array):
#     """Return list elements in an array whose first element matches the key."""
#     found_elements = []
#     for e in array:
#         try:
#             k = e[0].value().lower()
#         except (IndexError, AttributeError, TypeError):
#             pass
#         else:
#             if k == key:
#                 found_elements.append(e)
#     return found_elements


def find_by_key(key, array):
    """Return a list of array elements whose first element matches the key.

    Args:
        key (string): Slash-separated string of keys to search for.
        array (list): Nested list of lists where first member of each list is a key.

    Returns:
        list: Elements from the list with the matching key.
    """

    try:
        # Split off the first part of the key and leave the rest as a subkey.
        k, sub_key = key.split("/", 1)
    except ValueError:
        # No delimiter, so use the entire key with no subkey.
        k = key
        sub_key = None

    # Search the array for subarrays having the key as the first element.
    found_subarrays = []
    for subarray in array:
        try:
            # Get the first element of the subarray.
            e = subarray[0].value().lower()
        except (IndexError, AttributeError, TypeError):
            pass
        else:
            # Check the first element against the key.
            if e == key:
                if not sub_key:
                    # Found a match, so add the subarray to the list.
                    found_subarrays.append(subarray)
                else:
                    # Found a match, but must check subkeys for further matches.
                    found_subarrays.extend(find_by_key(sub_key, subarray))
    return found_subarrays


def get_value_by_key(key, array):
    """Return the value from a (key, value) list.

    Args:
        key (string): Key to search for.
        array (list): Nested list of lists where first element of each list is a key.

    Returns:
        object: Whatever element followed the key in the matching list.
    """
    try:
        value = find_by_key(key, array)[0][1]
    except IndexError:
        return None
    else:
        try:
            return value.value()
        except AttributeError:
            return value


def quote(s):
    """
    Returns a quoted version of string 's' if that's not already the case
    """

    if s is None:
        return s

    rx = r"^['\"](.*)['\"]$"

    if re.match(rx, s) is not None:
        return s
    else:
        return '"{}"'.format(s)


def unquote(s):
    """Remove any quote marks around a string.

    Args:
        s (string): Quoted or unquoted string.

    Returns:
        string: Unquoted string.
    """

    if not isinstance(s, basestring):
        return s  # Not a string, so just return it.
    try:
        # This returns inner part of "..." or '...' strings.
        return re.match("^(['\"])(.*)\\1$", s).group(2)
    except (IndexError, AttributeError):
        # No surrounding quotes, so just return string.
        return s


def explode(collapsed):
    """Explode collapsed references like 'C1-C3,C7,C10-C13' into [C1,C2,C3,C7,C10,C11,C12,C13].

    Args:
        collapsed (string): String of collapsed references.

    Returns:
        list: list of reference strings.
    """

    if collapsed == "":
        return []

    individual_refs = []
    if isinstance(collapsed, basestring):
        range_refs = re.split(",|;", collapsed)
        for r in range_refs:
            mtch = re.match(
                r"^\s*(?P<part_prefix>\D+)(?P<range_start>\d+)\s*[-:]\s*\1(?P<range_end>\d+)\s*$",
                r,
            )
            if mtch is None:
                individual_refs.append(r.strip())
            else:
                part_prefix = mtch.group("part_prefix")
                range_start = int(mtch.group("range_start"))
                range_end = int(mtch.group("range_end"))
                for i in range(range_start, range_end + 1):
                    individual_refs.append(part_prefix + str(i))

    return individual_refs


def collapse(individual_refs):
    """Collapse references like [C1,C2,C3,C7,C10,C11,C12,C13] into 'C1-C3, C7, C10-C13'.

    Args:
        individual_refs (string): Uncollapsed references.

    Returns:
        string: Collapsed references.
    """

    parts = []
    for ref in individual_refs:
        mtch = re.match(r"(?P<part_prefix>\D+)(?P<number>.+)", ref)
        if mtch is not None:
            part_prefix = mtch.group("part_prefix")
            number = mtch.group("number")
            try:
                number = int(mtch.group("number"))
            except ValueError:
                pass
            parts.append((part_prefix, number))

    parts.sort()

    def toRef(part):
        return "{}{}".format(part[0], part[1])

    def make_groups(accumulator, part):
        prev = None
        if len(accumulator) > 0:
            group = accumulator[-1]
            if len(group) > 0:
                prev = group[-1]
        if (prev != None) and (prev[0] == part[0]) and isinstance(prev[1], int) and ((prev[1] + 1) == part[1]):
            group.append(part)
            accumulator[-1] = group
        else:
            accumulator.append([part])
        return accumulator

    groups = reduce(make_groups, parts, [])
    groups = map(lambda g: tuple(map(toRef, g)), groups)

    collapsed = ""
    for group in groups:
        if (len(collapsed) > 1) and (collapsed[-2] != ","):
            collapsed += ", "
        if len(group) > 2:
            collapsed += group[0] + "-" + group[-1]
        else:
            collapsed += ", ".join(group)

    return collapsed


# Stores list of file names that have been backed-up before modification.
backedup_files = []


def create_backup(file):
    """Create a backup copy of a file.

    Args:
        file (string): Path to file.
    """

    if file in backedup_files:
        return

    if not os.path.isfile(file):
        return

    index = 1  # Start with this backup file suffix.
    while True:
        backup_file = "{}.{}.bak".format(file, index)
        if not os.path.isfile(backup_file):
            # Found an unused backup file name, so make backup.
            shutil.copy(file, backup_file)
            break  # Backup done, so break out of loop.
        index += 1  # Else keep looking for an unused backup file name.

    backedup_files.append(file)
