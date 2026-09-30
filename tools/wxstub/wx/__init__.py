"""Synthetic `wx` package for headless Ink/Stitch.

Ink/Stitch eagerly imports its GUI layer (which imports `wx`) even when running
headless for file export.  wxPython has no Linux wheels in this environment and
cannot be built (no C++ toolchain), and the GUI is never actually used for
machine-file export.  This package satisfies the import-time surface only.
"""

import importlib.abc
import importlib.machinery
import sys
import types


class _Meta(type):
    def __call__(cls, *args, **kwargs):
        return _Instance()

    def __or__(cls, other):
        return cls

    def __ror__(cls, other):
        return cls

    def __and__(cls, other):
        return cls

    def __rand__(cls, other):
        return cls

    def __add__(cls, other):
        return cls

    def __radd__(cls, other):
        return cls

    def __sub__(cls, other):
        return cls

    def __mul__(cls, other):
        return cls

    def __eq__(cls, other):
        return True

    def __ne__(cls, other):
        return False

    def __hash__(cls):
        return 0

    def __getattr__(cls, name):
        return _make(name)

    def __getitem__(cls, key):
        return _make("item")

    def __iter__(cls):
        return iter(())

    def __len__(cls):
        return 0

    def __bool__(cls):
        return True


_class_counter = 0


def _make(name):
    global _class_counter
    _class_counter += 1
    return _Meta("%s_%d" % (name, _class_counter), (_U,), {})


class _U(metaclass=_Meta):
    """Universal stand-in for any wx class."""


class _Instance:
    def __call__(self, *args, **kwargs):
        return _Instance()

    def __getattr__(self, name):
        return _U

    def __or__(self, other):
        return self

    def __and__(self, other):
        return self

    def __add__(self, other):
        return self

    def __sub__(self, other):
        return self

    def __mul__(self, other):
        return self

    def __radd__(self, other):
        return self

    def __getitem__(self, key):
        return _U

    def __iter__(self):
        return iter(())

    def __len__(self):
        return 0

    def __eq__(self, other):
        return True

    def __ne__(self, other):
        return False

    def __hash__(self):
        return 0

    def __bool__(self):
        return True

    def __nonzero__(self):
        return True


class _SubModule(types.ModuleType):
    def __getattr__(self, name):
        return _make(name)


class _Loader(importlib.abc.Loader):
    def create_module(self, spec):
        return _SubModule(spec.name)

    def exec_module(self, module):
        pass


class _Finder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "wx" or fullname.startswith("wx."):
            return importlib.machinery.ModuleSpec(
                fullname, _Loader(), is_package=(fullname == "wx")
            )


if not any(isinstance(f, _Finder) for f in sys.meta_path):
    sys.meta_path.insert(0, _Finder())

__all__ = []


def __getattr__(name):
    return _make(name)
