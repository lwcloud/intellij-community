# encoding: utf-8
"""
This thing tries to restore public interface of objects that don't have a python
source: C extensions and built-in objects. It does not reimplement the
'inspect' module, but complements it.

Since built-ins don't have many features that full-blown objects have, 
we do not support some fancier things like metaclasses.

We use certain kind of doc comments ("f(int) -> list") as a hint for functions'
input and output, especially in builtin functions.

This code has to work with CPython versions from 2.2 to 3.0+, and hopefully with
compatible versions of Jython and IronPython.

NOTE: Currently python 3 support is outright BROKEN, because bare asterisks and param decorators
are not parsed. This is deliberate in current version, since the rest of PyCharm does not support
all this too.
"""

from datetime import datetime

OUR_OWN_DATETIME = datetime(2010, 11, 26, 17, 14, 0) # datetime.now() of edit time
# we could use script's ctime, but the actual running copy may have it all wrong.
#
# Note: DON'T FORGET TO UPDATE!

import sys
import os
import string
import types
import atexit
import keyword

try:
    import inspect
except ImportError:
    inspect = None # it may fail

import re

if sys.platform == 'cli':
    import clr

version = (
    (sys.hexversion & (0xff << 24)) >> 24,
    (sys.hexversion & (0xff << 16)) >> 16
)

if version[0] >= 3:
    import builtins as the_builtins

    string = "".__class__
    #LETTERS = string_mod.ascii_letters
    STR_TYPES = (getattr(the_builtins, "bytes"), str)

    NUM_TYPES = (int, float)
    SIMPLEST_TYPES = NUM_TYPES + STR_TYPES + (None.__class__,)
    EASY_TYPES = NUM_TYPES + STR_TYPES + (None.__class__, dict, tuple, list)

    def the_exec(source, context):
        exec(source, context)

else: # < 3.0
    import __builtin__ as the_builtins
    #LETTERS = string_mod.letters
    STR_TYPES = (getattr(the_builtins, "unicode"), str)

    NUM_TYPES = (int, long, float)
    SIMPLEST_TYPES = NUM_TYPES + STR_TYPES + (types.NoneType,)
    EASY_TYPES = NUM_TYPES + STR_TYPES + (types.NoneType, dict, tuple, list)

    def the_exec(source, context):
        exec (source) in context

BUILTIN_MOD_NAME = the_builtins.__name__

if version[0] == 2 and version[1] < 4:
    HAS_DECORATORS = False

    def lstrip(s, prefix):
        i = 0
        while s[i] == prefix:
            i += 1
        return s[i:]

else:
    HAS_DECORATORS = True
    lstrip = string.lstrip

#
IDENT_PATTERN = "[A-Za-z_][0-9A-Za-z_]*" # re pattern for identifier
NUM_IDENT_PATTERN = re.compile("([A-Za-z_]+)[0-9]?[A-Za-z_]*") # 'foo_123' -> $1 = 'foo_'
STR_CHAR_PATTERN = "[0-9A-Za-z_.,\+\-&\*% ]"

DOC_FUNC_RE = re.compile("(?:.*\.)?(\w+)\(([^\)]*)\).*") # $1 = function name, $2 = arglist

SANE_REPR_RE = re.compile(IDENT_PATTERN + "(?:\(.*\))?") # identifier with possible (...), go catches

IDENT_RE = re.compile("(" + IDENT_PATTERN + ")") # $1 = identifier

STARS_IDENT_RE = re.compile("(\*?\*?" + IDENT_PATTERN + ")") # $1 = identifier, maybe with a * or **

IDENT_EQ_RE = re.compile("(" + IDENT_PATTERN + "\s*=)") # $1 = identifier with a following '='

SIMPLE_VALUE_RE = re.compile(
    "(\([+-]?[0-9](?:\s*,\s*[+-]?[0-9])*\))|" + # a numeric tuple, e.g. in pygame
    "([+-]?[0-9]+\.?[0-9]*(?:[Ee]?[+-]?[0-9]+\.?[0-9]*)?)|" + # number
    "('" + STR_CHAR_PATTERN + "*')|" + # single-quoted string
    '("' + STR_CHAR_PATTERN + '*")|' + # double-quoted string
    "(\[\])|" +
    "(\{\})|" +
    "(\(\))|" +
    "(True|False|None)"
) # $? = sane default value

def _searchbases(cls, accum):
# logic copied from inspect.py
    if cls not in accum:
        accum.append(cls)
        for x in cls.__bases__:
            _searchbases(x, accum)

def getMRO(a_class):
# logic copied from inspect.py
    "Returns a tuple of MRO classes."
    if hasattr(a_class, "__mro__"):
        return a_class.__mro__
    elif hasattr(a_class, "__bases__"):
        bases = []
        _searchbases(a_class, bases)
        return tuple(bases)
    else:
        return tuple()


def getBases(a_class): # TODO: test for classes that don't fit this scheme
    "Returns a sequence of class's bases."
    if hasattr(a_class, "__bases__"):
        return a_class.__bases__
    else:
        return ()


def isCallable(x):
    return hasattr(x, '__call__')


def sortedNoCase(p_array):
    "Sort an array case insensitevely, returns a sorted copy"
    p_array = list(p_array)
    if version[0] < 3:
        def c(x, y):
            x = x.upper()
            y = y.upper()
            if x > y:
                return 1
            elif x < y:
                return -1
            else:
                return 0

        p_array.sort(c)
    else:
        p_array.sort(key=lambda x: x.upper())

    return p_array

def cleanup(value):
    result = []
    prev = i = 0
    length = len(value)
    first_non_ascii = chr(127)
    while i < length:
        c = value[i]
        replacement = None
        if c == '\n':
            replacement = '\\n'
        elif c == '\r':
            replacement = '\\r'
        elif c < ' ' or c > first_non_ascii:
            replacement = '?' # NOTE: such chars are rare; long swaths could be precessed differently
        if replacement:
            result.append(value[prev:i])
            result.append(replacement)
        i+=1
    return "".join(result)

# http://blogs.msdn.com/curth/archive/2009/03/29/an-ironpython-profiler.aspx
def print_profile():
    data = []
    data.extend(clr.GetProfilerData())
    data.sort(lambda x, y: -cmp(x.ExclusiveTime, y.ExclusiveTime))
    for p in data:
        print('%s\t%d\t%d\t%d' % (p.Name, p.InclusiveTime, p.ExclusiveTime, p.Calls))

def is_clr_type(t):
    if not t: return False
    try:
        clr.GetClrType(t)
        return True
    except TypeError:
        return False

_prop_types = [type(property())]
try: _prop_types.append(types.GetSetDescriptorType)
except: pass

try: _prop_types.append(types.MemberDescriptorType)
except: pass

_prop_types = tuple(_prop_types)

def isProperty(x):
    return isinstance(x, _prop_types)

FAKE_CLASSOBJ_NAME = "___Classobj"

def sanitizeIdent(x, is_clr=False):
    "Takes an identifier and returns it sanitized"
    if x in ("class", "object", "def", "list", "tuple", "int", "float", "str", "unicode" "None"):
        return "p_" + x
    else:
        if is_clr:
            # it tends to have names like "int x", turn it to just x
            xs = x.split(" ")
            if len(xs) == 2:
              return sanitizeIdent(xs[1])
        return x.replace("-", "_").replace(" ", "_").replace(".", "_") # for things like "list-or-tuple" or "list or tuple"

def reliable_repr(value):
    # some subclasses of built-in types (see PyGtk) may provide invalid __repr__ implementations,
    # so we need to sanitize the output
    if isinstance(value, bool):
        return repr(bool(value))
    for t in NUM_TYPES:
        if isinstance(value, t):
            return repr(t(value))
    return repr(value)

def sanitizeValue(p_value):
    "Returns p_value or its part if it represents a sane simple value, else returns 'None'"
    if isinstance(p_value, STR_TYPES):
        match = SIMPLE_VALUE_RE.match(p_value)
        if match:
            return match.groups()[match.lastindex - 1]
        else:
            return 'None'
    elif isinstance(p_value, NUM_TYPES):
        return reliable_repr(p_value)
    elif p_value is None:
        return 'None'
    else:
        if hasattr(p_value, "__name__") and hasattr(p_value, "__module__") and p_value.__module__ == BUILTIN_MOD_NAME:
            return p_value.__name__ # float -> "float"
        else:
            return repr(repr(p_value)) # function -> "<function ...>", etc

def extractAlphaPrefix(p_string, default="some"):
    "Returns 'foo' for things like 'foo1' or 'foo2'; if prefix cannot be found, the default is returned"
    match = NUM_IDENT_PATTERN.match(p_string)
    name = match and match.groups()[match.lastindex - 1] or None
    return name or default


class FakeClassObj:
    "A mock class representing the old style class base."
    __module__ = None
    __class__ = None

    def __init__(self):
        pass

if version[0] < 3:
    from pyparsing import *
else:
    from pyparsing_py3 import *

# grammar to parse parameter lists

# // snatched from parsePythonValue.py, from pyparsing samples, copyright 2006 by Paul McGuire but under BSD license.
# we don't suppress lots of punctuation because we want it back when we reconstruct the lists

lparen, rparen, lbrack, rbrack, lbrace, rbrace, colon = map(Literal, "()[]{}:")

integer = Combine(Optional(oneOf("+ -")) + Word(nums))\
    .setName("integer")
real = Combine(Optional(oneOf("+ -")) + Word(nums) + "." +
               Optional(Word(nums)) +
               Optional(oneOf("e E")+Optional(oneOf("+ -")) +Word(nums)))\
    .setName("real")
tupleStr = Forward()
listStr = Forward()
dictStr = Forward()

boolLiteral = oneOf("True False")
noneLiteral = Literal("None")

listItem = real|integer|quotedString|unicodeString|boolLiteral|noneLiteral| \
            Group(listStr) | tupleStr | dictStr

tupleStr << ( Suppress("(") + Optional(delimitedList(listItem)) +
              Optional(Literal(",")) + Suppress(")") ).setResultsName("tuple")

listStr << (lbrack + Optional(delimitedList(listItem) +
                              Optional(Literal(","))) + rbrack).setResultsName("list")

dictEntry = Group(listItem + colon + listItem)
dictStr << (lbrace + Optional(delimitedList(dictEntry) + Optional(Literal(","))) + rbrace).setResultsName("dict")
# \\ end of the snatched part

# our output format is s-expressions:
# (simple name optional_value) is name or name=value
# (nested (simple ...) (simple ...)) is (name, name,...)
# (opt ...) is [, ...] or suchlike.

T_SIMPLE = 'Simple'
T_NESTED = 'Nested'
T_OPTIONAL = 'Opt'
T_RETURN = "Ret"

TRIPLE_DOT = '...'

COMMA = Suppress(",")
APOS = Suppress("'")
QUOTE = Suppress('"')
SP = Suppress(Optional(White()))

ident = Word(alphas + "_", alphanums + "_-.").setName("ident") # we accept things like "foo-or-bar"
decorated_ident = ident + Optional(Suppress(SP + Literal(":") + SP + ident)) # accept "foo: bar", ignore "bar"
spaced_ident = Combine(decorated_ident + ZeroOrMore(Literal(' ') + decorated_ident)) # we accept 'list or tuple' or 'C struct'

# allow quoted names, because __setattr__, etc docs use it
paramname = spaced_ident | \
            APOS + spaced_ident + APOS | \
            QUOTE + spaced_ident + QUOTE

parenthesized_tuple = ( Literal("(") + Optional(delimitedList(listItem, combine=True)) +
              Optional(Literal(",")) + Literal(")") ).setResultsName("(tuple)")


initializer = (SP + Suppress("=") + SP + Combine(parenthesized_tuple | listItem | ident )).setName("=init") # accept foo=defaultfoo

param = Group(Empty().setParseAction(replaceWith(T_SIMPLE)) + Combine(Optional(oneOf("* **")) + paramname) + Optional(initializer))

ellipsis = Group(
        Empty().setParseAction(replaceWith(T_SIMPLE))+ \
  (Literal("..") + \
  ZeroOrMore(Literal('.'))).setParseAction(replaceWith(TRIPLE_DOT)) # we want to accept both 'foo,..' and 'foo, ...'
        )

paramSlot = Forward()

simpleParamSeq = ZeroOrMore(paramSlot + COMMA) + Optional(paramSlot + Optional(COMMA))
nestedParamSeq = Group(
        Suppress('(').setParseAction(replaceWith(T_NESTED)) + \
  simpleParamSeq + Optional(ellipsis + Optional(COMMA) + Optional(simpleParamSeq)) + \
  Suppress(')')
        ) # we accept "(a1, ... an)"

paramSlot << (param | nestedParamSeq)

optionalPart = Forward()

paramSeq = simpleParamSeq + Optional(optionalPart) # this is our approximate target 

optionalPart << (
Group(
    Suppress('[').setParseAction(replaceWith(T_OPTIONAL)) + Optional(COMMA) + \
    paramSeq + Optional(ellipsis) + \
    Suppress(']')
  ) \
  | ellipsis
)

return_type = Group(
  Empty().setParseAction(replaceWith(T_RETURN)) +
  Suppress(SP + (Literal("->") | (Literal(":") + SP + Literal("return"))) + SP) +
  ident
)

# this is our ideal target, with balancing paren and a multiline rest of doc.
paramSeqAndRest = paramSeq + Suppress(')') + Optional(return_type) + Suppress(Optional(Regex(".*(?s)")))

_is_verbose = False # controlled by -v
def note(msg, *data):
    if _is_verbose:
        sys.stderr.write(msg % data)
        sys.stderr.write("\n")

_current_action = "nothing yet"
def action(msg, *data):
    global _current_action
    _current_action = msg % data
    note(msg, *data)

def transformSeq(results, toplevel=True):
    "Transforms a tree of ParseResults into a param spec string."
    is_clr = sys.platform == "cli"
    ret = [] # add here token to join
    for token in results:
        token_type = token[0]
        if token_type is T_SIMPLE:
            token_name = token[1]
            if len(token) == 3: # name with value
                if toplevel:
                    ret.append(sanitizeIdent(token_name, is_clr) + "=" + sanitizeValue(token[2]))
                else:
                    # smth like "a, (b1=1, b2=2)", make it "a, p_b"
                    return ["p_" + results[0][1]] # NOTE: for each item of tuple, return the same name of its 1st item.
            elif token_name == TRIPLE_DOT:
                if toplevel and not hasItemStartingWith(ret, "*"):
                    ret.append("*more")
                else:
                # we're in a "foo, (bar1, bar2, ...)"; make it "foo, bar_tuple"
                    return extractAlphaPrefix(results[0][1]) + "_tuple"
            else: # just name
                ret.append(sanitizeIdent(token_name, is_clr))
        elif token_type is T_NESTED:
            inner = transformSeq(token[1:], False)
            if len(inner) != 1:
                ret.append(inner)
            else:
                ret.append(inner[0]) # [foo] -> foo
        elif token_type is T_OPTIONAL:
            ret.extend(transformOptionalSeq(token))
        elif token_type is T_RETURN:
            pass # this is handled elsewhere
        else:
            raise Exception("This cannot be a token type: " + repr(token_type))
    return ret

def transformOptionalSeq(results):
    """
    Produces a string that describes the optional part of parameters.
    @param results must start from T_OPTIONAL.
    """
    assert results[0] is T_OPTIONAL, "transformOptionalSeq expects a T_OPTIONAL node, sees " + repr(results[0])
    is_clr = sys.platform == "cli"
    ret = []
    for token in results[1:]:
        token_type = token[0]
        if token_type is T_SIMPLE:
            token_name = token[1]
            if len(token) == 3: # name with value; little sense, but can happen in a deeply nested optional
                ret.append(sanitizeIdent(token_name, is_clr) + "=" + sanitizeValue(token[2]))
            elif token_name == '...':
            # we're in a "foo, [bar, ...]"; make it "foo, *bar"
                return ["*" + extractAlphaPrefix(results[1][1])] # we must return a seq; [1] is first simple, [1][1] is its name
            else: # just name
                ret.append(sanitizeIdent(token_name, is_clr) + "=None")
        elif token_type is T_OPTIONAL:
            ret.extend(transformOptionalSeq(token))
        # maybe handle T_NESTED if such cases ever occur in real life
        # it can't be nested in a sane case, really
    return ret

def flatten(seq):
    "Transforms tree lists like ['a', ['b', 'c'], 'd'] to strings like '(a, (b, c), d)', enclosing each tree level in parens."
    ret = []
    for one in seq:
        if type(one) is list:
            ret.append(flatten(one))
        else:
            ret.append(one)
    return "(" + ", ".join(ret) + ")"

def makeNamesUnique(seq, name_map=None):
    """
    Returns a copy of tree list seq where all clashing names are modified by numeric suffixes:
    ['a', 'b', 'a', 'b'] becomes ['a', 'b', 'a_1', 'b_1'].
    Each repeating name has its own counter in the name_map.
    """
    ret = []
    if not name_map:
        name_map = {}
    for one in seq:
        if type(one) is list:
            ret.append(makeNamesUnique(one, name_map))
        else:
            one_key = lstrip(one, "*") # starred parameters are unique sans stars
            if one_key in name_map:
                old_one = one_key
                one = one + "_" + str(name_map[old_one])
                name_map[old_one] += 1
            else:
                name_map[one_key] = 1
            ret.append(one)
    return ret

def hasItemStartingWith(p_seq, p_start):
    for item in p_seq:
        if isinstance(item, STR_TYPES) and item.startswith(p_start):
            return True
    return False

# return type inference helper table
INT_LIT =  '0'
FLOAT_LIT ='0.0'
DICT_LIT = '{}'
LIST_LIT = '[]'
TUPLE_LIT ='()'
BOOL_LIT = 'False'
RET_TYPE = { # {'type_name': 'value_string'} lookup table
    # chaining
    "self":    "self",
    "self.":   "self",
    # int
    "int":      INT_LIT,
    "Int":      INT_LIT,
    "integer":  INT_LIT,
    "Integer":  INT_LIT,
    "short":    INT_LIT,
    "long":     INT_LIT,
    "number":   INT_LIT,
    "Number":   INT_LIT,
    # float
    "float":    FLOAT_LIT,
    "Float":    FLOAT_LIT,
    "double":   FLOAT_LIT,
    "Double":   FLOAT_LIT,
    "floating": FLOAT_LIT,
    # boolean
    "bool":     BOOL_LIT,
    "boolean":  BOOL_LIT,
    "Bool":     BOOL_LIT,
    "Boolean":  BOOL_LIT,
    "True":     BOOL_LIT,
    "true":     BOOL_LIT,
    "False":    BOOL_LIT,
    "false":    BOOL_LIT,
    # list
    'list':     LIST_LIT,
    'List':     LIST_LIT,
    '[]':       LIST_LIT,
    # tuple
    "tuple":    TUPLE_LIT,
    "sequence": TUPLE_LIT,
    "Sequence": TUPLE_LIT,
    # dict
    "dict":       DICT_LIT,
    "Dict":       DICT_LIT,
    "dictionary": DICT_LIT,
    "Dictionary": DICT_LIT,
    "map":        DICT_LIT,
    "Map":        DICT_LIT,
    "hashtable":  DICT_LIT,
    "Hashtable":  DICT_LIT,
    "{}":         DICT_LIT,
    # "objects"
    "object":     "object()",
}
if version[0] < 3:
    UNICODE_LIT = 'u""'
    BYTES_LIT = '""'
    RET_TYPE.update({
        'string':   BYTES_LIT,
        'String':   BYTES_LIT,
        'str':      BYTES_LIT,
        'Str':      BYTES_LIT,
        'character':BYTES_LIT,
        'char':     BYTES_LIT,
        'unicode':  UNICODE_LIT,
        'Unicode':  UNICODE_LIT,
        'bytes':    BYTES_LIT,
        'byte':     BYTES_LIT,
        'Bytes':    BYTES_LIT,
        'Byte':     BYTES_LIT,
    })
    DEFAULT_STR_LIT = BYTES_LIT
    # also, files:
    RET_TYPE.update({
        'file': "file('/dev/null')",
    })
else:
    UNICODE_LIT = '""'
    BYTES_LIT = 'b""'
    RET_TYPE.update({
        'string':   UNICODE_LIT,
        'String':   UNICODE_LIT,
        'str':      UNICODE_LIT,
        'Str':      UNICODE_LIT,
        'character':UNICODE_LIT,
        'char':     UNICODE_LIT,
        'unicode':  UNICODE_LIT,
        'Unicode':  UNICODE_LIT,
        'bytes':    BYTES_LIT,
        'byte':     BYTES_LIT,
        'Bytes':    BYTES_LIT,
        'Byte':     BYTES_LIT,
    })
    DEFAULT_STR_LIT = UNICODE_LIT
    # also, files: we can't provide an easy expression on py3k
    RET_TYPE.update({
        'file': None,
    })

def packageOf(name, unqualified_ok=False):
    """
    packageOf('foo.bar.baz') = 'foo.bar.'
    packageOf('foo') = ''
    packageOf('foo', True) = 'foo'
    """
    if name:
        res = name[:name.rfind('.')+1]
        if not res and unqualified_ok:
            res = name
        return res
    else:
        return ''
    
class emptylistdict(dict):
    "defaultdict not available before 2.5; simplest reimplementation using [] as default"
    def __getitem__(self, item):
        if item in self:
            return dict.__getitem__(self, item)
        else:
            it = []
            self.__setitem__(item, it)
            return it



class Buf(object):
    "Buffers data in a list, can wrtie to a file. Indentation is provided externally."
    def __init__(self, indenter):
        self.data = []
        self.indenter = indenter

    def put(self, data):
        if data:
            self.data.append(str(data))

    def out(self, indent, *what):
        "Output the arguments, indenting as needed, and adding an eol"
        self.put(self.indenter.indent(indent))
        for item in what:
            self.put(item)
        self.put("\n")

    def flush(self, outfile):
        for x in self.data:
            outfile.write(x)

    def isEmpty(self):
        return len(self.data) == 0



class ModuleRedeclarator(object):
    def __init__(self, module, outfile, indent_size=4, doing_builtins=False):
        """
        Create new instance.
        @param module module to restore.
        @param outfile output file, must be open and writable.
        @param indent_size amount of space characters per indent
        """
        self.module = module
        self.outfile = outfile # where we finally write
        # we write things into buffers out-of-order
        self.header_buf = Buf(self)
        self.imports_buf = Buf(self)
        self.functions_buf = Buf(self)
        self.classes_buf = Buf(self)
        self.footer_buf = Buf(self)
        self.indent_size = indent_size
        self._indent_step = " " * indent_size
        #
        self.imported_modules = {"": the_builtins}
        self._defined = {} # stores True for every name defined so far, to break circular refs in values
        self.doing_builtins = doing_builtins
        self.ret_type_cache = {}
        self.used_imports = emptylistdict()
        # ^ maps qual_module_name -> [imported_names,..]

    def indent(self, level):
        "Return indentation whitespace for given level."
        return self._indent_step * level

    def flush(self):
        for buf in (self.header_buf, self.imports_buf, self.functions_buf, self.classes_buf, self.footer_buf):
            buf.flush(self.outfile)
            
    def outDocstring(self, out_func, docstring, indent):
        if isinstance(docstring, str):
            lines = docstring.strip().split("\n")
            if lines:
                if len(lines) == 1:
                    out_func(indent, '""" ' + lines[0] + ' """')
                else:
                    out_func(indent, '"""')
                    for line in lines:
                        out_func(indent, line)
                    out_func(indent, '"""')

    def outDocAttr(self, out_func, p_object, indent, p_class=None):
        the_doc = getattr(p_object, "__doc__", None)
        if the_doc:
            if p_class and the_doc == object.__init__.__doc__ and p_object is not object.__init__ and p_class.__doc__:
                the_doc = str(p_class.__doc__) # replace stock init's doc with class's; make it a certain string.
                the_doc += "\n# (copied from class doc)"
            self.outDocstring(out_func, the_doc, indent)
        else:
            out_func(indent, "# no doc")

    # Some values are known to be of no use in source and needs to be suppressed.
    # Dict is keyed by module names, with "*" meaning "any module";
    # values are lists of names of members whose value must be pruned.
    SKIP_VALUE_IN_MODULE = {
        "sys": (
            "modules", "path_importer_cache", "argv", "builtins",
            "last_traceback", "last_type", "last_value", "builtin_module_names",
        ),
        "posix": (
            "environ",
        ),
        "zipimport": (
            "_zip_directory_cache",
        ),
        "*":   (BUILTIN_MOD_NAME,)
    }

    # {"module": ("name",..)}: omit the names from the skeleton at all.
    OMIT_NAME_IN_MODULE = {}

    if version[0] >= 3:
        v = OMIT_NAME_IN_MODULE.get(BUILTIN_MOD_NAME, []) + ["True", "False", "None", "__debug__"]
        OMIT_NAME_IN_MODULE[BUILTIN_MOD_NAME] = v

    ADD_VALUE_IN_MODULE = {
        "sys": ("exc_value = Exception()", "exc_traceback=None"), # only present after an exception in current thread
    }

    # Some values are special and are better represented by hand-crafted constructs.
    # Dict is keyed by (module name, member name) and value is the replacement.
    REPLACE_MODULE_VALUES = {
        ("numpy.core.multiarray", "typeinfo") : "{}",
    }
    if version[0] <= 2:
        REPLACE_MODULE_VALUES[(BUILTIN_MOD_NAME, "None")] = "object()"
        for std_file in ("stdin", "stdout", "stderr"):
            REPLACE_MODULE_VALUES[("sys", std_file)] = "file('')" #

    # Some functions and methods of some builtin classes have special signatures.
    # {("class", "method"): ("signature_string")}
    PREDEFINED_BUILTIN_SIGS = {
        ("type", "__init__"): "(cls, what, bases=None, dict=None)", # two sigs squeezed into one
        ("object", "__init__"): "(self)",
        ("object", "__new__"): "(cls, *more)", # only for the sake of parameter names readability
        ("object", "__subclasshook__"): "(cls, subclass)", # trusting PY-1818 on sig
        ("int", "__init__"): "(self, x, base=10)", # overrides a fake
        ("list", "__init__"): "(self, seq=())",
        ("tuple", "__init__"): "(self, seq=())", # overrides a fake
        ("set", "__init__"): "(self, seq=())",
        ("dict", "__init__"): "(self, seq=None, **kwargs)",
        ("property", "__init__"): "(self, fget=None, fset=None, fdel=None, doc=None)", # TODO: infer, doc comments have it
        ("dict", "update"): "(self, E=None, **F)", # docstring nearly lies
        (None, "zip"): "(seq1, seq2, *more_seqs)",
        (None, "range"): "(start=None, stop=None, step=None)", # suboptimal: allows empty arglist
        (None, "filter"): "(function_or_none, sequence)",
        (None, "iter"): "(source, sentinel=None)",
        ('frozenset', "__init__"): "(seq=())",
    }

    if version[0] < 3:
        PREDEFINED_BUILTIN_SIGS[("unicode", "__init__")] = "(self, x, encoding=None, errors='strict')" # overrides a fake
        PREDEFINED_BUILTIN_SIGS[("super", "__init__")] = "(self, type1, type2=None)"
        PREDEFINED_BUILTIN_SIGS[(None, "min")] = "(*args, **kwargs)" # too permissive, but py2.x won't allow a better sig
        PREDEFINED_BUILTIN_SIGS[(None, "max")] = "(*args, **kwargs)"
        PREDEFINED_BUILTIN_SIGS[("str", "__init__")] = "(self, x)" # overrides a fake
    else:
        PREDEFINED_BUILTIN_SIGS[("super", "__init__")] = "(self, type1=None, type2=None)"
        PREDEFINED_BUILTIN_SIGS[(None, "min")] = "(*args, key=None)"
        PREDEFINED_BUILTIN_SIGS[(None, "max")] = "(*args, key=None)"
        PREDEFINED_BUILTIN_SIGS[(None, "open")] = "(file, mode='r', buffering=None, encoding=None, errors=None, newline=None, closefd=True)"
        PREDEFINED_BUILTIN_SIGS[("str", "__init__")] = "(self, value, encoding=None, errors='strict')" # overrides a fake
        PREDEFINED_BUILTIN_SIGS[("bytes", "__init__")] = "(self, value, encoding=None, errors='strict')" # overrides a fake

    if version == (2, 5):
        PREDEFINED_BUILTIN_SIGS[("unicode", "splitlines")] = "(keepends=None)" # a typo in docstring there

    # NOTE: per-module signature data may be lazily imported
    # keyed by (module_name, class_name, method_name). PREDEFINED_BUILTIN_SIGS might be a layer of it.
    # value is ("signature", "return_literal")
    PREDEFINED_MOD_CLASS_SIGS = {
        ("binascii", None, "hexlify"): ("(data)", BYTES_LIT),
        ("binascii", None, "unhexlify"): ("(hexstr)", BYTES_LIT),

        ("time", None, "ctime"): ("(seconds=None)", DEFAULT_STR_LIT),

        ("_collections", "deque", "__init__"): ("(self, iterable=(), maxlen=None)", None), # doc string blatantly lies

        ("datetime", "date", "__new__"): ("(cls, year=None, month=None, day=None)", None),
        ("datetime", "date", "fromordinal"): ("(cls, ordinal)", "date(1,1,1)"),
        ("datetime", "date", "fromtimestamp"): ("(cls, timestamp)", "date(1,1,1)"),
        ("datetime", "date", "isocalendar"): ("(self)", "(1, 1, 1)"),
        ("datetime", "date", "isoformat"): ("(self)", DEFAULT_STR_LIT),
        ("datetime", "date", "isoweekday"): ("(self)", INT_LIT),
        ("datetime", "date", "replace"): ("(self, year=None, month=None, day=None)", "date(1,1,1)"),
        ("datetime", "date", "strftime"): ("(self, format)", DEFAULT_STR_LIT),
        ("datetime", "date", "timetuple"): ("(self)", "(0, 0, 0, 0, 0, 0, 0, 0, 0)"),
        ("datetime", "date", "today"): ("(self)", "date(1, 1, 1)"),
        ("datetime", "date", "toordinal"): ("(self)", INT_LIT),
        ("datetime", "date", "weekday"): ("(self)", INT_LIT),
        ("datetime", "timedelta", "__new__"
        ): ("(cls, days=None, seconds=None, microseconds=None, milliseconds=None, minutes=None, hours=None, weeks=None)", None),
        ("datetime", "datetime", "__new__"
        ): ("(cls, year=None, month=None, day=None, hour=None, minute=None, second=None, microsecond=None, tzinfo=None)", None),
        ("datetime", "datetime", "astimezone"): ("(self, tz)", "datetime(1, 1, 1)"),
        ("datetime", "datetime", "combine"): ("(cls, date, time)", "datetime(1, 1, 1)"),
        ("datetime", "datetime", "date"): ("(self)", "datetime(1, 1, 1)"),
        ("datetime", "datetime", "fromtimestamp"): ("(cls, timestamp, tz=None)", "datetime(1, 1, 1)"),
        ("datetime", "datetime", "isoformat"): ("(self, sep='T')", DEFAULT_STR_LIT),
        ("datetime", "datetime", "now"): ("(cls, tz=None)", "datetime(1, 1, 1)"),
        ("datetime", "datetime", "strptime"): ("(cls, date_string, format)", DEFAULT_STR_LIT),
        ("datetime", "datetime", "replace" ):
          ("(self, year=None, month=None, day=None, hour=None, minute=None, second=None, microsecond=None, tzinfo=None)", "datetime(1, 1, 1)"),
        ("datetime", "datetime", "time"): ("(self)", "time(0, 0)"),
        ("datetime", "datetime", "timetuple"): ("(self)", "(0, 0, 0, 0, 0, 0, 0, 0, 0)"),
        ("datetime", "datetime", "timetz"): ("(self)", "time(0, 0)"),
        ("datetime", "datetime", "utcfromtimestamp"): ("(self, timestamp)", "datetime(1, 1, 1)"),
        ("datetime", "datetime", "utcnow"): ("(cls)", "datetime(1, 1, 1)"),
        ("datetime", "datetime", "utctimetuple"): ("(self)", "(0, 0, 0, 0, 0, 0, 0, 0, 0)"),
        ("datetime", "time", "__new__"): ("(cls, hour=None, minute=None, second=None, microsecond=None, tzinfo=None)", None),
        ("datetime", "time", "isoformat"): ("(self)", DEFAULT_STR_LIT),
        ("datetime", "time", "replace"): ("(self, hour=None, minute=None, second=None, microsecond=None, tzinfo=None)", "time(0, 0)"),
        ("datetime", "time", "strftime"): ("(self, format)", DEFAULT_STR_LIT),
        ("datetime", "tzinfo", "dst"): ("(self, date_time)", INT_LIT),
        ("datetime", "tzinfo", "fromutc"): ("(self, date_time)", "datetime(1, 1, 1)"),
        ("datetime", "tzinfo", "tzname"): ("(self, date_time)", DEFAULT_STR_LIT),
        ("datetime", "tzinfo", "utcoffset"): ("(self, date_time)", INT_LIT),

        # NOTE: here we stand on shaky ground providing sigs for 3rd-party modules, though well-known
        ("numpy.core.multiarray", "ndarray", "__array__") : ("(self, dtype=None)", None),
        ("numpy.core.multiarray", None, "arange") : ("(start=None, stop=None, step=None, dtype=None)", None), # same as range()
        ("numpy.core.multiarray", None, "set_numeric_ops") : ("(**ops)", None),
    }

    # known properties of modules
    # {{"module": {"class", "property" : ("letters", "getter")}},
    # where letters is any set of r,w,d (read, write, del) and "getter" is a source of typed getter.
    # if vlue is None, the property should be omitted.
    # read-only properties that return an object are not listed.
    G_OBJECT = "lambda self: object()"
    G_TYPE = "lambda self: type(object)"
    G_DICT = "lambda self: {}"
    G_STR = "lambda self: ''"
    G_TUPLE = "lambda self: tuple()"
    G_FLOAT = "lambda self: 0.0"
    G_INT = "lambda self: 0"
    G_BOOL = "lambda self: True"

    KNOWN_PROPS = {
        BUILTIN_MOD_NAME: {
            ("object", '__class__'): ('r', G_TYPE),
            ("BaseException", '__dict__'): ('r', G_DICT),
            ("BaseException", 'message'): ('rwd', G_STR),
            ("BaseException", 'args'): ('r', G_TUPLE),
            ('complex', 'real'): ('r', G_FLOAT),
            ('complex', 'imag'): ('r', G_FLOAT),
            ("EnvironmentError", 'errno'): ('rwd', G_INT),
            ("EnvironmentError", 'message'): ('rwd', G_STR),
            ("EnvironmentError", 'strerror'): ('rwd', G_INT),
            ("EnvironmentError", 'filename'): ('rwd', G_STR),
            ("file", 'softspace'): ('r', G_BOOL),
            ("file", 'name'): ('r', G_STR),
            ("file", 'encoding'): ('r', G_STR),
            ("file", 'mode'): ('r', G_STR),
            ("file", 'closed'): ('r', G_BOOL),
            ("file", 'newlines'): ('r', G_STR),
            ("SyntaxError", 'text'): ('rwd', G_STR),
            ("SyntaxError", 'print_file_and_line'): ('rwd', G_BOOL),
            ("SyntaxError", 'filename'): ('rwd', G_STR),
            ("SyntaxError", 'lineno'): ('rwd', G_INT),
            ("SyntaxError", 'offset'): ('rwd', G_INT),
            ("SyntaxError", 'msg'): ('rwd', G_STR),
            ("SyntaxError", 'message'): ('rwd', G_STR),
            ("slice", 'start'): ('r', G_INT),
            ("slice", 'step'): ('r', G_INT),
            ("slice", 'stop'): ('r', G_INT),
            ("super", '__thisclass__'): ('r', G_TYPE),
            ("super", '__self__'): ('r', G_TYPE),
            ("super", '__self_class__'): ('r', G_TYPE),
            ("SystemExit", 'message'): ('rwd', G_STR),
            ("SystemExit", 'code'): ('rwd', G_OBJECT),
            ("type", '__basicsize__'): ('r', G_INT),
            ("type", '__itemsize__'): ('r', G_INT),
            ("type", '__base__'): ('r', G_TYPE),
            ("type", '__flags__'): ('r', G_INT),
            ("type", '__mro__'): ('r', G_TUPLE),
            ("type", '__bases__'): ('r', G_TUPLE),
            ("type", '__dictoffset__'): ('r', G_INT),
            ("type", '__dict__'): ('r', G_DICT),
            ("type", '__name__'): ('r', G_STR),
            ("type", '__weakrefoffset__'): ('r', G_INT),
            ("UnicodeDecodeError", '__basicsize__'): None,
            ("UnicodeDecodeError", '__itemsize__'): None,
            ("UnicodeDecodeError", '__base__'): None,
            ("UnicodeDecodeError", '__flags__'): ('rwd', G_INT),
            ("UnicodeDecodeError", '__mro__'): None,
            ("UnicodeDecodeError", '__bases__'): None,
            ("UnicodeDecodeError", '__dictoffset__'): None,
            ("UnicodeDecodeError", '__dict__'): None,
            ("UnicodeDecodeError", '__name__'): None,
            ("UnicodeDecodeError", '__weakrefoffset__'): None,
            ("UnicodeEncodeError", 'end'): ('rwd', G_INT),
            ("UnicodeEncodeError", 'encoding'): ('rwd', G_STR),
            ("UnicodeEncodeError", 'object'): ('rwd', G_OBJECT),
            ("UnicodeEncodeError", 'start'): ('rwd', G_INT),
            ("UnicodeEncodeError", 'reason'): ('rwd', G_STR),
            ("UnicodeEncodeError", 'message'): ('rwd', G_STR),
            ("UnicodeTranslateError", 'end'): ('rwd', G_INT),
            ("UnicodeTranslateError", 'encoding'): ('rwd', G_STR),
            ("UnicodeTranslateError", 'object'): ('rwd', G_OBJECT),
            ("UnicodeTranslateError", 'start'): ('rwd', G_INT),
            ("UnicodeTranslateError", 'reason'): ('rwd', G_STR),
            ("UnicodeTranslateError", 'message'): ('rwd', G_STR),
        },
        '_ast': {
            ("AST", '__dict__'): ('rd', G_DICT),
        },
        'posix': {
            ("statvfs_result", 'f_flag'): ('r', G_INT),
            ("statvfs_result", 'f_bavail'): ('r', G_INT),
            ("statvfs_result", 'f_favail'): ('r', G_INT),
            ("statvfs_result", 'f_files'): ('r', G_INT),
            ("statvfs_result", 'f_frsize'): ('r', G_INT),
            ("statvfs_result", 'f_blocks'): ('r', G_INT),
            ("statvfs_result", 'f_ffree'): ('r', G_INT),
            ("statvfs_result", 'f_bfree'): ('r', G_INT),
            ("statvfs_result", 'f_namemax'): ('r', G_INT),
            ("statvfs_result", 'f_bsize'): ('r', G_INT),

            ("stat_result", 'st_ctime'): ('r', G_INT),
            ("stat_result", 'st_rdev'): ('r', G_INT),
            ("stat_result", 'st_mtime'): ('r', G_INT),
            ("stat_result", 'st_blocks'): ('r', G_INT),
            ("stat_result", 'st_gid'): ('r', G_INT),
            ("stat_result", 'st_nlink'): ('r', G_INT),
            ("stat_result", 'st_ino'): ('r', G_INT),
            ("stat_result", 'st_blksize'): ('r', G_INT),
            ("stat_result", 'st_dev'): ('r', G_INT),
            ("stat_result", 'st_size'): ('r', G_INT),
            ("stat_result", 'st_mode'): ('r', G_INT),
            ("stat_result", 'st_uid'): ('r', G_INT),
            ("stat_result", 'st_atime'): ('r', G_INT),
        },
        "pwd": {
            ("struct_pwent", 'pw_dir'): ('r', G_STR),
            ("struct_pwent", 'pw_gid'): ('r', G_INT),
            ("struct_pwent", 'pw_passwd'): ('r', G_STR),
            ("struct_pwent", 'pw_gecos'): ('r', G_STR),
            ("struct_pwent", 'pw_shell'): ('r', G_STR),
            ("struct_pwent", 'pw_name'): ('r', G_STR),
            ("struct_pwent", 'pw_uid'): ('r', G_INT),

            ("struct_passwd", 'pw_dir'): ('r', G_STR),
            ("struct_passwd", 'pw_gid'): ('r', G_INT),
            ("struct_passwd", 'pw_passwd'): ('r', G_STR),
            ("struct_passwd", 'pw_gecos'): ('r', G_STR),
            ("struct_passwd", 'pw_shell'): ('r', G_STR),
            ("struct_passwd", 'pw_name'): ('r', G_STR),
            ("struct_passwd", 'pw_uid'): ('r', G_INT),
        },
        "thread": {
            ("_local", '__dict__'): None
        },
        "xxsubtype": {
            ("spamdict", 'state'): ('r', G_INT),
            ("spamlist", 'state'): ('r', G_INT),
        },
        "zipimport": {
            ("zipimporter", 'prefix'): ('r', G_STR),
            ("zipimporter", 'archive'): ('r', G_STR),
            ("zipimporter", '_files'): ('r', G_DICT),
        },
        "datetime": {
            ("datetime", "hour"): ('r', G_INT),
            ("datetime", "minute"): ('r', G_INT),
            ("datetime", "second"): ('r', G_INT),
            ("datetime", "microsecond"): ('r', G_INT),
        },
    }

    # modules that seem to re-export names but surely don't
    # ("qualified_module_name",..)
    KNOWN_FAKE_REEXPORTERS = (
      "gtk._gtk",
      "gobject._gobject",
      "numpy.core.multiarray",
      "numpy.core._dotblas",
      "numpy.core.umath",
    )

    # Some builtin classes effectively change __init__ signature without overriding it.
    # This callable serves as a placeholder to be replaced via REDEFINED_BUILTIN_SIGS
    def fake_builtin_init(self): pass # just a callable, sig doesn't matter

    fake_builtin_init.__doc__ = object.__init__.__doc__ # this forces class's doc to be used instead

    # This is a list of builtin classes to use fake init
    FAKE_BUILTIN_INITS = (tuple, type, int, str)
    if version[0] < 3:
        import __builtin__ as b2

        FAKE_BUILTIN_INITS = FAKE_BUILTIN_INITS + (getattr(b2, "unicode"),)
        del b2
    else:
        import builtins as b2

        FAKE_BUILTIN_INITS = FAKE_BUILTIN_INITS + (getattr(b2, "str"), getattr(b2, "bytes"))
        del b2

    # Some builtin methods are decorated, but this is hard to detect.
    # {("class_name", "method_name"): "decorator"}
    KNOWN_DECORATORS = {
        ("dict", "fromkeys"): "staticmethod",
        ("object", "__subclasshook__"): "classmethod",
    }

    def isSkippedInModule(self, p_module, p_value):
        "Returns True if p_value's value must be skipped for module p_module."
        skip_list = self.SKIP_VALUE_IN_MODULE.get(p_module, [])
        if p_value in skip_list:
            return True
        skip_list = self.SKIP_VALUE_IN_MODULE.get("*", [])
        if p_value in skip_list:
            return True
        return False


    def findImportedName(self, item):
        """
        Finds out how the item is represented in imported modules.
        @param item what to check
        @return qualified name (like "sys.stdin") or None
        """
        # TODO: return a pair, not a glued string
        if not isinstance(item, SIMPLEST_TYPES):
            for mname in self.imported_modules:
                m = self.imported_modules[mname]
                for inner_name in m.__dict__:
                    suspect = getattr(m, inner_name)
                    if suspect is item:
                        if mname:
                            mname += "."
                        elif self.module is the_builtins: # don't short-circuit builtins
                            return None
                        return mname + inner_name
        return None

    _initializers = (
      (dict, "{}"),
      (tuple, "()"),
      (list, "[]"),
    )
    def inventInitializer(self, a_type):
      """
      Returns an innocuous initializer expression for a_type, or "None"
      """
      for t, r in self._initializers:
          if t == a_type:
              return r
      # NOTE: here we could handle things like defaultdict, sets, etc if we wanted
      return "None"


    def fmtValue(self, out, p_value, indent, prefix="", postfix="", as_name=None, seen_values=None):
        """
        Formats and outputs value (it occupies an entire line or several lines).
        @param out function that does output (a Buf.out)
        @param p_value the value.
        @param indent indent level.
        @param prefix text to print before the value
        @param postfix text to print after the value
        @param as_name hints which name are we trying to print; helps with circular refs.
        @param seen_values a list of keys we've seen if we're processing a dict
        """
        SELF_VALUE = "<value is a self-reference, replaced by this string>"
        if isinstance(p_value, SIMPLEST_TYPES):
            out(indent, prefix, reliable_repr(p_value), postfix)
        else:
            if sys.platform == "cli":
                imported_name = None
            else:
                imported_name = self.findImportedName(p_value)
            if imported_name:
                out(indent, prefix, imported_name, postfix)
                # TODO: kind of self.used_imports[imported_name].append(p_value) but split imported_name
                # else we could potentially return smth we did not otherwise import. but not likely.
            else:
                if isinstance(p_value, (list, tuple)):
                    if not seen_values:
                        seen_values = [p_value]
                    if len(p_value) == 0:
                        out(indent, prefix, repr(p_value), postfix)
                    else:
                        if isinstance(p_value, list):
                            lpar, rpar = "[", "]"
                        else:
                            lpar, rpar = "(", ")"
                        out(indent, prefix, lpar)
                        for v in p_value:
                            if v in seen_values:
                                v = SELF_VALUE
                            elif not isinstance(v, SIMPLEST_TYPES):
                                seen_values.append(v)
                            self.fmtValue(out, v, indent + 1, postfix=",", seen_values=seen_values)
                        out(indent, rpar, postfix)
                elif isinstance(p_value, dict):
                    if len(p_value) == 0:
                        out(indent, prefix, repr(p_value), postfix)
                    else:
                        if not seen_values:
                          seen_values = [p_value]
                        out(indent, prefix, "{")
                        keys = list(p_value.keys())
                        try:
                            keys.sort()
                        except TypeError:
                            pass # unsortable keys happen, e,g, in py3k _ctypes
                        for k in keys:
                            v = p_value[k]
                            if v in seen_values:
                                v = SELF_VALUE
                            elif not isinstance(v, SIMPLEST_TYPES):
                                seen_values.append(v)
                            if isinstance(k, SIMPLEST_TYPES):
                                self.fmtValue(out, v, indent + 1, prefix=repr(k) + ": ", postfix=",", seen_values=seen_values)
                            else:
                                # both key and value need fancy formatting
                                self.fmtValue(out, k, indent + 1, postfix=": ", seen_values=seen_values)
                                self.fmtValue(out, v, indent + 2, seen_values=seen_values)
                                out(indent + 1, ",")
                        out(indent, "}", postfix)
                else: # something else, maybe representable
                    # look up this value in the module.
                    if sys.platform == "cli":
                        out(indent, prefix, "None", postfix)
                        return
                    found_name = ""
                    for inner_name in self.module.__dict__:
                        if self.module.__dict__[inner_name] is p_value:
                            found_name = inner_name
                            break
                    if self._defined.get(found_name, False):
                        out(indent, prefix, found_name, postfix)
                    else:
                    # a forward / circular declaration happens
                        notice = ""
                        s = cleanup(repr(p_value))
                        if found_name:
                            if found_name == as_name:
                                notice = " # (!) real value is %r" % s
                                s = "None"
                            else:
                                notice = " # (!) forward: %s, real value is %r" % (found_name, s)
                        if SANE_REPR_RE.match(s):
                            out(indent, prefix, s, postfix, notice)
                        else:
                            if not found_name:
                                notice = " # (!) real value is %r" % s
                            out(indent, prefix, "None", postfix, notice)


    def getRetType(self, s):
        """
        Returns a return type string as given by T_RETURN in tokens, or None
        """
        if s:
            v = RET_TYPE.get(s, None)
            if v:
                return v
            thing = getattr(self.module, s, None)
            if thing:
                return s
            # adds no noticeable slowdown, I did measure. dch.
            for im_name, im_module in self.imported_modules.items():
                cache_key = (im_name, s)
                cached = self.ret_type_cache.get(cache_key, None)
                if cached:
                  return cached
                v = getattr(im_module, s, None)
                if v:
                    if isinstance(v, type):
                        # detect a constructor
                        constr_args = self.detectConstructor(v)
                        if constr_args is None:
                            constr_args = "*(), **{}" # a silly catch-all constructor
                        ref = "%s(%s)" % (s, constr_args)
                    else:
                        ref = s
                    if im_name:
                        result = "%s.%s" % (im_name, ref)
                    else: # built-in
                        result = ref
                    self.ret_type_cache[cache_key] = result
                    return result
            # TODO: handle things like "[a, b,..] and (foo,..)"
        return None

    def detectConstructor(self, p_class):
        # try to inspect the thing
        constr = getattr(p_class, "__init__")
        if constr and inspect and inspect.isfunction(constr):
            args, _, _, _ = inspect.getargspec(constr)
            return ", ".join(args)
        else:
            return None

    SIG_DOC_NOTE = "restored from __doc__"
    SIG_DOC_UNRELIABLY = "NOTE: unreliably restored from __doc__ "

    def restoreByDocString(self, signature_string, class_name, deco=None, ret_hint=None):
        """
        @param signature_string: parameter list extracted from the doc string.
        @param class_name: name of the containing class, or None
        @param deco: decorator to use
        @param ret_hint: return type hint, if available
        @return (reconstructed_spec, return_type, note) or (None, _, _) if failed.
        """
        action("restoring func %r of class %r", signature_string, class_name)
        # parse
        parsing_failed = False
        ret_type = None
        try:
            # strict parsing
            tokens = paramSeqAndRest.parseString(signature_string, True)
            ret_name = None
            if tokens:
              ret_t = tokens[-1]
              if ret_t[0] is T_RETURN:
                ret_name = ret_t[1]
            ret_type = self.getRetType(ret_name) or self.getRetType(ret_hint)
        except ParseException:
            # it did not parse completely; scavenge what we can
            parsing_failed = True
            tokens = []
            try:
                # most unrestrictive parsing
                tokens = paramSeq.parseString(signature_string, False)
            except ParseException:
                pass
            #
        seq = transformSeq(tokens)

        # add safe defaults for unparsed
        if parsing_failed:
            note = self.SIG_DOC_UNRELIABLY
            starred = None
            double_starred = None
            for one in seq:
                if type(one) is str:
                    if one.startswith("**"):
                        double_starred = one
                    elif one.startswith("*"):
                        starred = one
            if not starred:
                seq.append("*args")
            if not double_starred:
                seq.append("**kwargs")
        else:
            note = self.SIG_DOC_NOTE

        # add 'self' if needed YYY
        if class_name and (not seq or seq[0] != 'self'):
            first_param = self.proposeFirstParam(deco)
            if first_param:
                seq.insert(0, first_param)
        seq = makeNamesUnique(seq)
        return (seq, ret_type, note)

    def parseFuncDoc(self, func_doc, func_id, func_name, class_name, deco=None, sip_generated=False):
        """
        @param func_doc: __doc__ of the function.
        @param func_id: name to look for as identifier of the function in docstring
        @param func_name: name of the function.
        @param class_name: name of the containing class, or None
        @param deco: decorator to use
        @return (reconstructed_spec, return_literal, note) or (None, _, _) if failed.
        """
        if sip_generated:
            overloads = []
            for l in func_doc.split('\n'):
                signature = func_id + '('
                i = l.find(signature)
                if i >= 0:
                    overloads.append(l[i+len(signature):])
            if len(overloads) > 1:
                docstring_results = [self.restoreByDocString(s, class_name, deco) for s in overloads]
                ret_types = []
                for result in docstring_results:
                    rt = result[1]
                    if rt and rt not in ret_types:
                        ret_types.append(rt)
                if ret_types:
                    ret_literal = " or ".join(ret_types)
                else:
                    ret_literal = None
                param_lists = [result[0] for result in docstring_results]
                spec = self.buildSignature(func_name, self.restoreParametersForOverloads(param_lists))
                return (spec, ret_literal, "restored from __doc__ with multiple overloads")

        # find the first thing to look like a definition
        prefix_re = re.compile("\s*(?:(\w+)[ \\t]+)?" + func_id + "\s*\(") # "foo(..." or "int foo(..."
        match = prefix_re.search(func_doc)
        # parse the part that looks right
        if match:
            ret_hint = match.group(1)
            params, ret_literal, note = self.restoreByDocString(func_doc[match.end():], class_name, deco, ret_hint)
            spec = func_name + flatten(params)
            return (spec, ret_literal, note)
        else:
            return (None, None, None)

    def isPredefinedBuiltin(self, module_name, class_name, func_name):
        return self.doing_builtins and module_name == BUILTIN_MOD_NAME and (class_name, func_name) in self.PREDEFINED_BUILTIN_SIGS

    def restorePredefinedBuiltin(self, class_name, func_name):
        spec = func_name + self.PREDEFINED_BUILTIN_SIGS[(class_name, func_name)]
        note = "known special case of " + (class_name and class_name + "." or "") + func_name
        return (spec, note)

    def restoreByInspect(self, p_func):
        "Returns paramlist restored by inspect."
        args, varg, kwarg, defaults = inspect.getargspec(p_func)
        spec = []
        if defaults:
            dcnt = len(defaults) - 1
        else:
            dcnt = -1
        args = args or []
        args.reverse() # backwards, for easier defaults handling
        for arg in args:
            if dcnt >= 0:
                arg += "=" + sanitizeValue(defaults[dcnt])
                dcnt -= 1
            spec.insert(0, arg)
        if varg:
            spec.append("*" + varg)
        if kwarg:
            spec.append("**" + kwarg)
        return flatten(spec)

    def restoreParametersForOverloads(self, parameter_lists):
        param_index = 0
        star_args = False
        optional = False
        params = []
        while True:
            parameter_lists_copy = [pl for pl in parameter_lists]
            for pl in parameter_lists_copy:
                if param_index >= len(pl):
                    parameter_lists.remove(pl)
                    optional = True
            if not parameter_lists:
                break
            name = parameter_lists[0][param_index]
            for pl in parameter_lists[1:]:
                if pl[param_index] != name:
                    star_args = True
                    break
            if star_args: break
            if optional and not '=' in name:
                params.append(name + '=None')
            else:
                params.append(name)
            param_index += 1
        if star_args:
            params.append("*__args")
        return params

    def buildSignature(self, p_name, params):
        return p_name + '(' + ', '.join(params) + ')'

    def restoreClr(self, p_name, p_class):
        """Restore the function signature by the CLR type signature"""
        clr_type = clr.GetClrType(p_class)
        if p_name == '__new__':
            methods = [c for c in clr_type.GetConstructors()]
            if not methods:
                return p_name + '(*args)', 'cannot find CLR constructor'
        else:
            methods = [m for m in clr_type.GetMethods() if m.Name == p_name]
            if not methods:
                bases = p_class.__bases__
                if len(bases) == 1 and p_name in dir(bases[0]):
                # skip inherited methods
                    return None, None
                return p_name + '(*args)', 'cannot find CLR method'

        parameter_lists = []
        for m in methods:
            parameter_lists.append([p.Name for p in m.GetParameters()])
        params = self.restoreParametersForOverloads(parameter_lists)
        if not methods[0].IsStatic:
            params = ['self'] + params
        return self.buildSignature(p_name, params), None

    def redoFunction(self, out, p_func, p_name, indent, p_class=None, p_modname=None, seen=None):
        """
        Restore function argument list as best we can.
        @param out output function of a Buf
        @param p_func function or method object
        @param p_name function name as known to owner
        @param indent indentation level
        @param p_class the class that contains this function as a method
        @param p_modname module name
        @param seen {func: name} map of functions already seen in the same namespace
        """
        action("redoing func %r of class %r", p_name, p_class)
        if seen is not None:
            other_func = seen.get(p_func, None)
            if other_func and getattr(other_func, "__doc__", None) is getattr(p_func, "__doc__", None):
                # _bisect.bisect == _bisect.bisect_right in py31, but docs differ
                out(indent, p_name, " = ", seen[p_func])
                out(indent, "")
                return
            else:
                seen[p_func] = p_name
        # real work
        classname = p_class and p_class.__name__ or None
        if p_class and hasattr(p_class, '__mro__'):
            sip_generated = [t for t in p_class.__mro__ if 'sip.simplewrapper' in str(t)]
        else:
            sip_generated = False
        deco = None
        deco_comment = ""
        mod_class_method_tuple = (p_modname, classname, p_name)
        ret_literal = None
        # any decorators?
        if self.doing_builtins and p_modname == BUILTIN_MOD_NAME:
            deco = self.KNOWN_DECORATORS.get((classname, p_name), None)
            if deco:
                deco_comment = " # known case"
        elif p_class and p_name in p_class.__dict__:
            # detect native methods declared with METH_CLASS flag
            descriptor = p_class.__dict__[p_name]
            if p_name != "__new__" and type(descriptor).__name__.startswith('classmethod' ):
                # 'classmethod_descriptor' in Python 2.x and 3.x, 'classmethod' in Jython
                deco = "classmethod"
            elif type(p_func).__name__.startswith('staticmethod'):
                deco = "staticmethod"
        if p_name == "__new__":
            deco = "staticmethod"
            deco_comment = " # known case of __new__"

        if deco and HAS_DECORATORS:
            out(indent, "@", deco, deco_comment)
        if inspect and inspect.isfunction(p_func):
            out(indent, "def ", p_name, self.restoreByInspect(p_func), ": # reliably restored by inspect", )
            self.outDocAttr(out, p_func, indent + 1, p_class)
        elif self.isPredefinedBuiltin(*mod_class_method_tuple):
            spec, sig_note = self.restorePredefinedBuiltin(classname, p_name)
            out(indent, "def ", spec, ": # ", sig_note)
            self.outDocAttr(out, p_func, indent + 1, p_class)
        elif sys.platform == 'cli' and is_clr_type(p_class):
            spec, sig_note = self.restoreClr(p_name, p_class)
            if not spec: return
            if sig_note:
                out(indent, "def ", spec, ": #", sig_note)
            else:
                out(indent, "def ", spec, ":")
            if not p_name in ['__gt__', '__ge__', '__lt__', '__le__', '__ne__', '__reduce_ex__', '__str__']:
                self.outDocAttr(out, p_func, indent + 1, p_class)
        elif mod_class_method_tuple in self.PREDEFINED_MOD_CLASS_SIGS:
            sig, ret_literal = self.PREDEFINED_MOD_CLASS_SIGS[mod_class_method_tuple]
            if classname:
                ofwhat = "%s.%s.%s" % mod_class_method_tuple
            else:
                ofwhat = "%s.%s" % (p_modname, p_name)
            out(indent, "def ", p_name, sig, ": # known case of ", ofwhat)
            self.outDocAttr(out, p_func, indent + 1, p_class)
        else:
        # __doc__ is our best source of arglist
            sig_note = "real signature unknown"
            spec = ""
            is_init = (p_name == "__init__" and p_class is not None)
            funcdoc = None
            if is_init and hasattr(p_class, "__doc__"):
                if hasattr(p_func, "__doc__"):
                    funcdoc = p_func.__doc__
                if funcdoc == object.__init__.__doc__:
                    funcdoc = p_class.__doc__
            elif hasattr(p_func, "__doc__"):
                funcdoc = p_func.__doc__
            sig_restored = False
            if isinstance(funcdoc, STR_TYPES):
                (spec, ret_literal, more_notes) = self.parseFuncDoc(funcdoc, p_name, p_name, classname, deco, sip_generated)
                if spec is None and p_name == '__init__' and classname:
                    (spec, ret_literal, more_notes) = self.parseFuncDoc(funcdoc, classname, p_name, classname, deco, sip_generated)
                sig_restored = spec is not None
                if more_notes:
                    if sig_note:
                        sig_note += "; "
                    sig_note += more_notes
            if not sig_restored:
            # use an allow-all declaration
                decl = []
                if p_class:
                    first_param = self.proposeFirstParam(deco)
                    if first_param:
                        decl.append(first_param)
                decl.append("*args")
                decl.append("**kwargs")
                spec = p_name + "(" + ", ".join(decl) + ")"
            out(indent, "def ", spec, ": # ", sig_note)
            # to reduce size of stubs, don't output same docstring twice for class and its __init__ method
            if not is_init or funcdoc != p_class.__doc__:
                self.outDocstring(out, funcdoc, indent + 1)
        # body
        if ret_literal:
          out(indent + 1, "return ", ret_literal)
        else:
          out(indent + 1, "pass" )
        if deco and not HAS_DECORATORS:
            out(indent, p_name, " = ", deco, "(", p_name, ")", deco_comment)
        out(0, "") # empty line after each item

    def proposeFirstParam(self, deco):
        "@return: name of missing first paramater, considering a decorator"
        if deco is None:
            return "self"
        if deco == "classmethod":
            return "cls"
        # if deco == "staticmethod":
        return None

    def fullName(self, cls, p_modname):
        m = cls.__module__
        if m == p_modname or m == BUILTIN_MOD_NAME or m == 'exceptions':
            return cls.__name__
        return m + "." + cls.__name__

    def redoClass(self, out, p_class, p_name, indent, p_modname=None, seen=None):
        """
        Restores a class definition.
        @param out output function of a relevant buf
        @param p_class the class object
        @param p_name class name as known to owner
        @param indent indentation level
        @param p_modname name of module
        @param seen {class: name} map of classes already seen in the same namespace
        """
        action("redoing class %r of module %r", p_name, p_modname)
        if seen is not None:
            if p_class in seen:
                out(indent, p_name, " = ", seen[p_class])
                out(indent, "")
                return
            else:
                seen[p_class] = p_name
        bases = getBases(p_class)
        base_def = ""
        if bases:
            base_def = "(" + ", ".join([self.fullName(x, p_modname) for x in bases]) + ")"
        out(indent, "class ", p_name, base_def, ":")
        self.outDocAttr(out, p_class, indent + 1)
        # inner parts
        methods = {}
        properties = {}
        others = {}
        we_are_the_base_class = p_modname == BUILTIN_MOD_NAME and p_name in ("object", FAKE_CLASSOBJ_NAME)
        has_dict = hasattr(p_class, "__dict__")
        if has_dict:
            field_source = p_class.__dict__
        else:
            field_source = dir(p_class) # this includes unwanted inherited methods, but no dict + inheritance is rare
        for item_name in field_source:
            if item_name in ("__doc__", "__module__"):
                if we_are_the_base_class:
                    item = "" # must be declared in base types
                else:
                    continue # in all other cases must be skipped
            elif keyword.iskeyword(item_name):  # for example, PyQt4 contains definitions of methods named 'exec'
                continue
            else:
                try:
                    item = getattr(p_class, item_name) # let getters do the magic
                except AttributeError:
                    item = field_source[item_name] # have it raw
            if isCallable(item):
                methods[item_name] = item
            elif isProperty(item):
                properties[item_name] = item
            else:
                others[item_name] = item
            #
        if we_are_the_base_class:
            others["__dict__"] = {} # force-feed it, for __dict__ does not contain a reference to itself :)
        # add fake __init__s to have the right sig
        if p_class in self.FAKE_BUILTIN_INITS:
            methods["__init__"] = self.fake_builtin_init
        elif '__init__' not in methods:
            init_method = getattr(p_class, '__init__', None)
            if init_method:
                methods['__init__'] = init_method

        #
        seen_funcs = {}
        for item_name in sortedNoCase(methods.keys()):
            item = methods[item_name]
            self.redoFunction(out, item, item_name, indent + 1, p_class, p_modname, seen=seen_funcs)
        #
        known_props = self.KNOWN_PROPS.get(p_modname, {})
        a_setter = "lambda self, v: None"
        a_deleter = "lambda self: None"
        for item_name in sortedNoCase(properties.keys()):
            prop_key = (p_name, item_name)
            if prop_key in known_props:
                prop_descr = known_props.get(prop_key, None)
                if prop_descr is None:
                    continue # explicitly omitted
                acc_line, getter = prop_descr
                accessors = []
                accessors.append("r" in acc_line and getter or "None")
                accessors.append("w" in acc_line and a_setter or "None")
                accessors.append("d" in acc_line and a_deleter or "None")
                out(indent+1, item_name, " = property(", ", ".join(accessors), ")")
            else:
                out(indent+1, item_name, " = property(lambda self: object(), None, None) # default")
            # TODO: handle prop's docstring
        if properties:
            out(0, "") # empty line after the block
        #
        for item_name in sortedNoCase(others.keys()):
            item = others[item_name]
            self.fmtValue(out, item, indent + 1, prefix=item_name + " = ")
        if others:
            out(0, "") # empty line after the block
        #
        if not methods and not properties and not others:
            out(indent + 1, "pass")


    def redoSimpleHeader(self, p_name):
        "Puts boilerplate code on the top"
        out = self.header_buf.out # 1st class methods rule :)
        out(0, "# encoding: utf-8") # NOTE: maybe encoding should be selectable
        if hasattr(self.module, "__name__"):
            self_name = self.module.__name__
            if self_name != p_name:
                mod_name = " calls itself " + self_name
            else:
                mod_name = ""
        else:
            mod_name = " does not know its name"
        if p_name == BUILTIN_MOD_NAME and version[0] == 2 and version[1] >= 6:
            out(0, "from __future__ import print_function")
        out(0, "# module " + p_name + mod_name)
        if hasattr(self.module, "__file__"):
            out(0, "# from file " + self.module.__file__)
        self.outDocAttr(out, self.module, 0)

    def addImportHeaderIfNeeded(self):
        if self.imports_buf.isEmpty():
            self.imports_buf.out(0, "")
            self.imports_buf.out(0, "# imports")

    def redo(self, p_name, imported_module_names):
        """
        Restores module declarations.
        Intended for built-in modules and thus does not handle import statements.
        @param p_name name of module
        """
        action("redong module %r", p_name)
        self.redoSimpleHeader(p_name)
        # find whatever other self.imported_modules the module knows; effectively these are imports
        module_type = type(sys)
        for item_name, item in self.module.__dict__.items():
            if isinstance(item, module_type):
                self.imported_modules[item_name] = item
                self.addImportHeaderIfNeeded()
                ref_notice = getattr(item, "__file__", str(item))
                if hasattr(item, "__name__"):
                    self.imports_buf.out(0, "import ", item.__name__, " as ", item_name, " # ", ref_notice)
                else:
                    self.imports_buf.out(0, item_name, " = None # ??? name unknown; ", ref_notice)

        # group what else we have into buckets
        vars_simple = {}
        vars_complex = {}
        funcs = {}
        classes = {}
        our_package = packageOf(p_name)
        for item_name in self.module.__dict__:
            if item_name in ("__dict__", "__doc__", "__module__", "__file__", "__name__", "__builtins__", "__package__"):
                continue # handled otherwise
            try:
                item = getattr(self.module, item_name) # let getters do the magic
            except AttributeError:
                item = self.module.__dict__[item_name] # have it raw
            # check if it has percolated from an imported module
            # unless we're adamantly positive that the name was imported, we assume it is defined here
            mod_name = None # module from which p_name might have been imported
            # IronPython has non-trivial reexports in System module, but not in others:
            skip_modname = sys.platform == "cli" and p_name != "System"
            # can't figure weirdness in some modules, assume no reexports:
            skip_modname =  skip_modname or p_name in self.KNOWN_FAKE_REEXPORTERS
            if not skip_modname:
                try:
                    mod_name = getattr(item, '__module__', None)
                except NameError:
                    pass
            import_from_top = our_package.startswith(packageOf(mod_name, True)) # e.g. p_name="pygame.rect" and mod_name="pygame"
            want_to_import = False
            if (mod_name \
                and mod_name not in BUILTIN_MOD_NAME \
                and mod_name != p_name \
                and not import_from_top\
            ):
                # import looks valid, but maybe it's a .py file? we're cenrtain not to import from .py
                # e.g. this rules out _collections import collections and builtins import site.
                try:
                    imported = __import__(mod_name) # ok to repeat, Python caches for us
                    if imported:
                        qualifieds = name.split(".")[1:]
                        for qual in qualifieds:
                            imported = getattr(imported, qual, None)
                            if not imported:
                                break
                        imported_path = getattr(imported, '__file__', "").lower()
                        note("path of %r is %r", mod_name, imported_path)
                        want_to_import = not (imported_path.endswith(".py") or imported_path.endswith(".pyc"))
                except ImportError:
                    want_to_import = False
                # NOTE: if we fail to import, we define 'imported' names here lest we lose them at all
                if want_to_import:
                    import_list = self.used_imports[mod_name]
                    if item_name not in import_list:
                        import_list.append(item_name)
            if not want_to_import:
                if isinstance(item, type) or item is FakeClassObj: # some classes are callable, check them before functions
                    classes[item_name] = item
                elif isCallable(item):
                    funcs[item_name] = item
                elif isinstance(item, module_type):
                    continue # self.imported_modules handled above already
                else:
                    if isinstance(item, SIMPLEST_TYPES):
                        vars_simple[item_name] = item
                    else:
                        vars_complex[item_name] = item
        #
        # sort and output every bucket
        self.outputImportFroms()
        #
        omitted_names = self.OMIT_NAME_IN_MODULE.get(p_name, [])
        if vars_simple:
            out = self.functions_buf.out
            prefix = "" # try to group variables by common prefix
            PREFIX_LEN = 2 # default prefix length if we can't guess better
            out(0, "# Variables with simple values")
            for item_name in sortedNoCase(vars_simple.keys()):
                if item_name in omitted_names:
                  out(0, "# definition of " + item_name + " omitted")
                  continue
                item = vars_simple[item_name]
                # track the prefix
                if len(item_name) >= PREFIX_LEN:
                    prefix_pos = string.rfind(item_name, "_") # most prefixes end in an underscore
                    if prefix_pos < 1:
                        prefix_pos = PREFIX_LEN
                    beg = item_name[0:prefix_pos]
                    if prefix != beg:
                        out(0, "") # space out from other prefix
                        prefix = beg
                else:
                    prefix = ""
                # output
                replacement = self.REPLACE_MODULE_VALUES.get((p_name, item_name), None)
                if replacement is not None:
                    out(0, item_name, " = ", replacement, " # real value of type ", str(type(item)), " replaced")
                elif self.isSkippedInModule(p_name, item_name):
                    t_item = type(item)
                    out(0, item_name, " = ", self.inventInitializer(t_item),  " # real value of type ", str(t_item), " skipped")
                else:
                    self.fmtValue(out, item, 0, prefix=item_name + " = ")
                self._defined[item_name] = True
            out(0, "") # empty line after vars
        #
        if funcs:
            out = self.functions_buf.out
            out(0, "# functions")
            out(0, "")
            seen_funcs = {}
            for item_name in sortedNoCase(funcs.keys()):
                if item_name in omitted_names:
                  out(0, "# definition of ", item_name, " omitted")
                  continue
                item = funcs[item_name]
                self.redoFunction(out, item, item_name, 0, p_modname=p_name, seen=seen_funcs)
                self._defined[item_name] = True
                out(0, "") # empty line after each item
        else:
            self.functions_buf.out(0, "# no functions")
        #
        if classes:
            out = self.functions_buf.out
            out(0, "# classes")
            out(0, "")
            seen_classes = {}
            # sort classes so that inheritance order is preserved
            cls_list = [] # items are (class_name, mro_tuple)
            for cls_name in sortedNoCase(classes.keys()):
                cls = classes[cls_name]
                ins_index = len(cls_list)
                for i in range(ins_index):
                    maybe_child_bases = cls_list[i][1]
                    if cls in maybe_child_bases:
                        ins_index = i # we could not go farther than current ins_index
                        break         # ...and need not go fartehr than first known child
                cls_list.insert(ins_index, (cls_name, getMRO(cls)))
            for item_name in [cls_item[0] for cls_item in cls_list]:
                if item_name in omitted_names:
                  out(0, "# definition of ", item_name, " omitted")
                  continue
                item = classes[item_name]
                self.redoClass(out, item, item_name, 0, p_modname=p_name, seen=seen_classes)
                self._defined[item_name] = True
                out(0, "") # empty line after each item
        else:
            self.classes_buf.out(0, "# no classes")
        #
        if vars_complex:
            out = self.footer_buf.out
            out(0, "# variables with complex values")
            out(0, "")
            for item_name in sortedNoCase(vars_complex.keys()):
                if item_name in omitted_names:
                  out(0, "# definition of " + item_name + " omitted")
                  continue
                item = vars_complex[item_name]
                replacement = self.REPLACE_MODULE_VALUES.get((p_name, item_name), None)
                if replacement is not None:
                    out(0, item_name + " = " + replacement + " # real value of type " + str(type(item)) + " replaced")
                elif self.isSkippedInModule(p_name, item_name):
                    t_item = type(item)
                    out(0, item_name + " = " + self.inventInitializer(t_item) +  " # real value of type " + str(t_item) + " skipped")
                else:
                    self.fmtValue(out, item, 0, prefix=item_name + " = ", as_name=item_name)
                self._defined[item_name] = True
                out(0, "") # empty line after each item
        values_to_add = self.ADD_VALUE_IN_MODULE.get(p_name, None)
        if values_to_add:
            self.footer_buf.out(0, "# intermittent names")
            for v in values_to_add:
                self.footer_buf.out(0, v)
        if self.imports_buf.isEmpty():
            self.imports_buf.out(0, "# no imports")
        self.imports_buf.out(0, "") # empty line after imports

    def outputImportFroms(self):
        "Mention all imported names known within the module, wrapping as per PEP."
        if self.used_imports:
            self.addImportHeaderIfNeeded()
            for mod_name in sortedNoCase(self.used_imports.keys()):
                names = self.used_imports[mod_name]
                if names:
                    self._defined[mod_name] = True
                    right_pos = 0 # tracks width of list to fold it at right margin
                    import_heading = "from % s import " % mod_name
                    right_pos += len(import_heading)
                    names_pack = [import_heading]
                    indent_level = 0
                    for n in sorted(names):
                        self._defined[n] = True
                        len_n = len(n)
                        if right_pos + len_n >= 78:
                            self.imports_buf.out(indent_level, *names_pack)
                            names_pack = [n, ", "]
                            if indent_level == 0:
                                indent_level = 1 # all but first line is indented
                            right_pos = self.indent_size + len_n + 2
                        else:
                            names_pack.append(n)
                            names_pack.append(", ")
                            right_pos += (len_n + 2)
                    if names_pack: # last line
                        self.imports_buf.out(indent_level, *names_pack[:-1]) # cut last comma

            self.imports_buf.out(0, "") # empty line after group




def buildOutputName(subdir, name):
    global action
    quals = name.split(".")
    dirname = subdir
    if dirname:
        dirname += os.path.sep # "a -> a/"
    for pathindex in range(len(quals) - 1): # create dirs for all quals but last
        subdirname = dirname + os.path.sep.join(quals[0: pathindex + 1])
        if not os.path.isdir(subdirname):
            action("creating subdir %r", subdirname)
            os.makedirs(subdirname)
        init_py = os.path.join(subdirname, "__init__.py")
        if os.path.isfile(subdirname + ".py"):
            os.rename(subdirname + ".py", init_py)
        elif not os.path.isfile(init_py):
            init = fopen(init_py, "w")
            init.close()
    target_dir = dirname + os.path.sep.join(quals[0: len(quals) - 1])
    #sys.stderr.write("target dir is " + repr(target_dir) + "\n")
    target_name = target_dir + os.path.sep + quals[-1]
    if os.path.isdir(target_name):
        fname = os.path.join(target_name, "__init__.py")
    else:
        fname = target_name + ".py"
    return fname

def redoModule(name, fname, imported_module_names):
    global action
    # gobject does 'del _gobject' in its __init__.py, so the chained attribute lookup code
    # fails to find 'gobject._gobject'. thus we need to pull the module directly out of
    # sys.modules
    mod = sys.modules[name]
    if not mod:
        sys.stderr.write("Failed to find imported module in sys.modules")
        #sys.exit(0)

    if update_mode and hasattr(mod, "__file__"):
        action("probing %r", fname)
        mod_mtime = os.path.exists(mod.__file__) and os.path.getmtime(mod.__file__) or 0.0
        file_mtime = os.path.exists(fname) and os.path.getmtime(fname) or 0.0
        # skeleton's file is no older than module's, and younger than our script
        if file_mtime >= mod_mtime and datetime.fromtimestamp(file_mtime) > OUR_OWN_DATETIME:
            return # skip the file

    if doing_builtins and name == BUILTIN_MOD_NAME:
        action("grafting")
        setattr(mod, FAKE_CLASSOBJ_NAME, FakeClassObj)
    action("opening %r", fname)
    outfile = fopen(fname, "w")
    action("restoring")
    r = ModuleRedeclarator(mod, outfile, doing_builtins=doing_builtins)
    r.redo(name, imported_module_names)
    action("flushing")
    r.flush()
    action("closing %r", fname)
    outfile.close()


# command-line interface

if __name__ == "__main__":
    from getopt import getopt
    import os

    if sys.version_info[0] > 2:
        import io  # in 3.0

        fopen = lambda name, mode: io.open(name, mode, encoding='utf-8')
    else:
        fopen = open

    # handle cmdline
    helptext = (
        'Generates interface skeletons for python modules.' '\n'
        'Usage: generator [options] [name ...]' '\n'
        'Every "name" is a (qualified) module name, e.g. "foo.bar"' '\n'
        'Output files will be named as modules plus ".py" suffix.' '\n'
        'Normally every name processed will be printed and stdout flushed.' '\n'
        'Options are:' '\n'
        ' -h -- prints this help message.' '\n'
        ' -d dir -- output dir, must be writable. If not given, current dir is used.' '\n'
        ' -b -- use names from sys.builtin_module_names' '\n'
        ' -q -- quiet, do not print anything on stdout. Errors still go to stderr.' '\n'
        ' -u -- update, only recreate skeletons for newer files, and skip unchanged.' '\n'
        ' -x -- die on exceptions with a stacktrace; only for debugging.' '\n'
        ' -v -- be verbose, print lots of debug output to stderr' '\n'
        ' -c modules -- import CLR assemblies with specified names' '\n'
        ' -p -- run CLR profiler ' '\n'
    )
    opts, fnames = getopt(sys.argv[1:], "d:hbquxvc:p")
    opts = dict(opts)
    if not opts or '-h' in opts:
        print(helptext)
        sys.exit(0)
    if '-b' not in opts and not fnames:
        sys.stderr.write("Neither -b nor any module name given\n")
        sys.exit(1)
    quiet = '-q' in opts
    update_mode = "-u" in opts
    debug_mode = "-x" in opts
    _is_verbose = '-v' in opts
    subdir = opts.get('-d', '')
    # determine names
    names = fnames
    if '-b' in opts:
        doing_builtins = True
        names.extend(sys.builtin_module_names)
        if not BUILTIN_MOD_NAME in names:
            names.append(BUILTIN_MOD_NAME)
        if '__main__' in names:
            names.remove('__main__') # we don't want ourselves processed
    else:
        doing_builtins = False

    if sys.platform == 'cli':
        refs = opts.get('-c', '')
        if refs:
            for ref in refs.split(';'): clr.AddReferenceByPartialName(ref)

        if '-p' in opts:
            atexit.register(print_profile)

        from System import DateTime

        start = DateTime.Now

    # go on
    for name in names:
        if name.endswith(".py"):
          sys.stderr.write("Ignored a regular Python file " + name + "\n")
          continue
        if not quiet:
            sys.stdout.write(name + "\n")
            sys.stdout.flush()
        action("doing nothing")
        try:
            fname = buildOutputName(subdir, name)

            old_modules = list(sys.modules.keys())
            imported_module_names = []
            class MyFinder:
                def find_module(self, fullname, path=None):
                    if fullname != name:
                        imported_module_names.append(fullname)
                    return None

            my_finder = None
            if hasattr(sys, 'meta_path'):
                my_finder = MyFinder()
                sys.meta_path.append(my_finder)
            else:
                imported_module_names = None

            action("importing %r", name)
            try:
                __import__(name) # sys.modules will fill up with what we want
            except ImportError:
                sys.stderr.write("Name " + name + " failed to import\n")
                continue

            if my_finder:
                sys.meta_path.remove(my_finder)
            if imported_module_names is None:
                imported_module_names = [m for m in sys.modules.keys() if m not in old_modules]

            redoModule(name, fname, imported_module_names)
            # The C library may have called Py_InitModule() multiple times to define several modules (gtk._gtk and gtk.gdk);
            # restore all of them
            if imported_module_names:
                for m in sys.modules.keys():
                    action("restoring submodule %r", m)
                    # if module has __file__ defined, it has Python source code and doesn't need a skeleton 
                    if m not in old_modules and m not in imported_module_names and m != name and not hasattr(sys.modules[m], '__file__'):
                        if not quiet:
                            sys.stdout.write(m + "\n")
                            sys.stdout.flush()
                        fname = buildOutputName(subdir, m)
                        redoModule(m, fname, imported_module_names)
        except:
            sys.stderr.write("Failed to process " + name + " while " + _current_action + "\n")
            if debug_mode:
                raise
            else:
                continue

    if sys.platform == 'cli':
        print("Generation completed in " + str((DateTime.Now - start).TotalMilliseconds) + " ms")
