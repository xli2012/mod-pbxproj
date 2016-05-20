# MIT License
#
# Copyright (c) 2016 Ignacio Calderon aka kronenthaler
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import os
import re


class DynamicObject(object):
    """
    Generic class that creates internal attributes to match the structure of the tree used to create the element.
    Also, prints itself using the openstep format. Extensions might be required to insert comments on right places.
    """
    _VALID_KEY_REGEX = '[a-zA-Z0-9\\._/-]*'

    def parse(self, value):
        if isinstance(value, dict):
            return self._parse_dict(value)

        return value

    def _parse_dict(self, obj):
        # all top level objects are added as variables to this object
        for key, value in obj.iteritems():
            if not hasattr(self, key):
                setattr(self, key, self._get_instance(key, value))

        return self

    def _get_instance(self, type, content):
        # check if the key maps to a kind of object
        module = __import__("mod_pbxproj2")
        if hasattr(module, type):
            class_ = getattr(module, type)
            return class_().parse(content)

        return DynamicObject().parse(content)

    def __repr__(self):
        return self._print_object()

    def _print_object(self, indentation_depth="", entry_separator='\n', object_start='\n', indentation_increment='\t'):
        ret = "{" + object_start
        # TODO: move isa key if present to the first position.
        for key in [x for x in dir(self) if not x.startswith("_") and not hasattr(getattr(self, x), '__call__')]:
            value = getattr(self, key)
            if hasattr(value, '_print_object'):
                value = value._print_object(indentation_depth + indentation_increment)
            elif isinstance(value, list):
                value = self._print_list(value, indentation_depth + indentation_increment)
            else:
                value = DynamicObject._escape(value.__str__())

            # use key decorators, could simplify the generation of the comments.
            ret += indentation_depth + "{3}{0} = {1};{2}".format(DynamicObject._escape(key), value, entry_separator, indentation_increment)
        ret += indentation_depth + "}"
        return ret

    def _print_list(self, value, indentation_depth="", single_line=False):
        entry_separator = object_start = "\n"
        indentation_increment = "\t"

        if single_line:
            entry_separator = " "
            object_start = indentation_increment = ""

        ret = "(" + object_start
        for item in value:
            ret += indentation_depth + "{1}{0},{2}".format(item, indentation_increment, entry_separator)
        ret += indentation_depth + ")"
        return ret

    @classmethod
    def _escape(cls, item):
        if re.match(cls._VALID_KEY_REGEX, item).group(0) != item:
            return '"{0}"'.format(item)
        return item


class objects(DynamicObject):
    # section priorities PBXBuildFile > PBXFileReference > ...
    def __init__(self):
        # sections: dict<isa, [tuple(id, obj)]>
        # sections get aggregated under the isa type. Each contains a list of tuples (id, obj) with every object defined
        self._sections = {}

    def parse(self, object):
        # iterate over the keys and fill the sections
        if isinstance(object, dict):
            for key, value in object.iteritems():
                obj_type = key
                if 'isa' in value:
                    obj_type = value['isa']

                child = self._get_instance(obj_type, value)
                if child.isa not in self._sections:
                    self._sections[child.isa] = []

                node = (key, child)
                self._sections[child.isa].append(node)

            return self

        # safe-guard: delegate to the parent how to deal with non-object values
        return super(type(self), self).parse(object)

    def _print_object(self, indentation_depth="", entry_separator='\n', object_start='\n', indentation_increment='\t'):
        # override to change the way the object is printed out
        result = "{\n"
        # TODO: sort sections alphabetically
        for section, phase in self._sections.iteritems():
            result += "\n/* Begin {0} section */\n".format(section)
            for (key, value) in phase:
                obj = value._print_object(indentation_depth + "\t", entry_separator, object_start, indentation_increment)
                result += indentation_depth + "\t{0} = {1};\n".format(key, obj)
            result += "/* End {0} section */\n".format(section)
        result += indentation_depth + "}"
        return result


class PBXBuildFile(DynamicObject):
    def _print_object(self, indentation_depth="", entry_separator='\n', object_start='\n', indentation_increment='\t'):
        return super(type(self), self)._print_object("", entry_separator=' ', object_start='', indentation_increment='')


class PBXFileReference(DynamicObject):
    def _print_object(self, indentation_depth="", entry_separator='\n', object_start='\n', indentation_increment='\t'):
        return super(type(self), self)._print_object("", entry_separator=' ', object_start='', indentation_increment='')


class XcodeProject(DynamicObject):
    """
    Top level class, handles the project CRUD operations, new, load, save, delete. Also, exposes methods to manipulate
    the project's content, add/remove files, add/remove libraries/frameworks, query sections. For more advanced
    operations, underlying objects are exposed that can be manipulated using said objects.
    """
    def __init__(self, tree=None, path=None):
        if path is None:
            path = os.path.join(os.getcwd(), 'project.pbxproj')

        self._pbxproj_path = os.path.abspath(path)
        self._source_root = os.path.abspath(os.path.join(os.path.split(path)[0], '..'))

        # initialize the structure using the given tree
        self.parse(tree)

    def save(self, path=None):
        if path is None:
            path = self._pbxproj_path

        f = open(path, 'w')
        f.write(self.__repr__())
        f.close()

    @classmethod
    def load(cls, path, pure_python=False):
        if pure_python:
            import openstep_parser as osp

            tree = osp.OpenStepDecoder.ParseFromFile(open(path, 'r'))
        else:
            import plistlib
            import subprocess

            plutil_path = os.path.join(os.path.split(__file__)[0], 'plutil')

            if not os.path.isfile(plutil_path):
                plutil_path = 'plutil'

            # load project by converting to xml and then convert that using plistlib
            p = subprocess.Popen([plutil_path, '-convert', 'xml1', '-o', '-', path], stdout=subprocess.PIPE)
            stdout, stderr = p.communicate()

            # If the plist was malformed, return code will be non-zero
            if p.returncode != 0:
                print stdout
                return None

            tree = plistlib.readPlistFromString(stdout)

        return XcodeProject(tree, path)


# if __name__ == "__main__":
#     # print XcodeProject({"a": "b", "c": {"1": 2},"z":[1,2,4]})
#     obj = XcodeProject.load('../mod_pbxproj/tests/samples/cloud-search.pbxproj')
#     print type(obj)
#     print obj