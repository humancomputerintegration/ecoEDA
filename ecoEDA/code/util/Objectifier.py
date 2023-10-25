####################################################################################################
#
# KiCad-RW — Python library to read/write KiCad Sexpr file format
# Copyright (C) 2021 Fabrice Salvaire
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
####################################################################################################

__all__ = [
]

####################################################################################################

import logging

import sexpdata
from sexpdata import car, cdr, Symbol

####################################################################################################

_module_logger = logging.getLogger(__name__)

####################################################################################################

def car_value(_):
    return car(_).value()

####################################################################################################

class TreeMixin:

    ##############################################

    def __init__(self):
        self._childs = []

    ##############################################

    def __bool__(self):
        return bool(self._childs)

    def __len__(self):
        return len(self._childs)

    def __iter__(self):
        return iter(self._childs)

    ##############################################

    @property
    def childs(self):
        return list(self._childs)

    @property
    def first_child(self):
        # if self._childs:
        return self._childs[0]
        # else:
        #     return None

    ##############################################

    def append_child(self, child):
        self._childs.append(child)

    ##############################################

    def depth_first_search(self, on_node=None, on_leaf=None, on_leave=None):
        go = True
        if on_node:
            go = on_node(self)
        if go:
            # print('-->')
            for child in self:
                if isinstance(child, Node):
                    child.depth_first_search(on_node, on_leaf, on_leave)
                elif on_leaf:
                    on_leaf(child)
            # print('<--')
            if on_leave:
                on_leave(self)

####################################################################################################

class Node(TreeMixin):

    ##############################################

    def __init__(self, path):
        super().__init__()
        self._path = path

    ##############################################

    @property
    def name(self):
        return self._path[-1]

    @property
    def path(self):
        return self._path

    @property
    def path_str(self):
        return '/'.join(self._path)

    @property
    def parent_str(self):
        _ = self._path[:-1]
        if _:
            return '/'.join(_)
        return '/'

    ##############################################

    def __str__(self):
        return f"{self.path_str}: {self.childs}"

    def __repr__(self):
        return f"{self.path_str}: {self.childs}"

    ##############################################

    def xpath(self, path):

        DEBUG = False

        if path.startswith('/'):
            path = path[1:]
            index = 0
        else:
            # relative
            index = -1
        parts = path.split('/')
        last_index = len(parts) -1
        if DEBUG:
            print(parts, last_index)

        results = []

        def on_node(node):
            nonlocal index
            if index == -1:
                index = 0
                return True
            if DEBUG:
                indent = '    '*index
                print(indent, '@', index+1, node.path_str)
            if node.name == parts[index]:
                if DEBUG:
                    print(indent, '  match')
                if index == last_index:
                    if DEBUG:
                        print(indent, '  found')
                    results.append(node)
                    return False
                index += 1
                return True
            return False

        def on_leave(node):
            nonlocal index
            if DEBUG:
                indent = '    '*index
                print(indent, '<<<@', index+1, 'leave')
            index -= 1

        self.depth_first_search(on_node, on_leave=on_leave)
        return results

####################################################################################################

class SchemaNode(TreeMixin):

    NODES = {}

    ##############################################

    @classmethod
    def get_node(cls, node):
        if not cls.NODES:
            cls.NODES['/'] = SchemaNode('/')
        path_str = node.path_str
        if path_str in cls.NODES:
            return cls.NODES[path_str]
        else:
            schema_node = SchemaNode(node.name)
            cls.NODES[path_str] = schema_node
            parent = cls.NODES[node.parent_str]
            parent.append_child(schema_node)

    ##############################################

    def __init__(self, name):
        super().__init__()
        self._name = name

    ##############################################

    @property
    def name(self):
        return self._name

    ##############################################

    def __repr__(self):
        return self._name

####################################################################################################

class Objectifier:

    _logger = _module_logger.getChild('Objectifier')

    ##############################################

    def __init__(self, path):

        self._logger.info(f"Load {path}")
        with open(path) as fh:
            sexpr = sexpdata.load(fh)

        self._root = self._walk_sexpr(sexpr)

    ##############################################

    @property
    def root(self):
        return self._root

    ##############################################

    def dump(self, root=None):
        if root is None:
            root = self._root
        def on_node(node):
            print(node.path_str)
            return True
        def on_leaf(leaf):
            print(f"    {leaf}")
        root.depth_first_search(on_node, on_leaf)

    ##############################################

    def get_paths(self, root=None):
        if root is None:
            root = self._root
        paths = set()
        def on_node(node):
            paths.add(node.path_str)
            return True
        root.depth_first_search(on_node)
        for _ in sorted(paths):
            print(_)

    ##############################################

    def get_schema(self, root=None):
        if root is None:
            root = self._root
        def on_node(node):
            SchemaNode.get_node(node)
            return True
        def on_leaf(leaf):
            pass
        root.depth_first_search(on_node, on_leaf)

    ##############################################

    def _walk_sexpr(self, sexpr, path=[]):
        """Perform a depth first search"""
        if isinstance(sexpr, (str, int, float)):
            return sexpr
        elif isinstance(sexpr, Symbol):
            return sexpr   # ??? .value()
        elif isinstance(sexpr, list):
            _car = car(sexpr).value()
            _cdr = cdr(sexpr)
            path = path.copy()
            path.append(_car)
            node = Node(path)
            for element in _cdr:
                child = self._walk_sexpr(element, path)
                node.append_child(child)
            return node
        else:
            raise ValueError()
