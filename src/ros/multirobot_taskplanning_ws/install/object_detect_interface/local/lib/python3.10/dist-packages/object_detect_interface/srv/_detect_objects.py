# generated from rosidl_generator_py/resource/_idl.py.em
# with input from object_detect_interface:srv/DetectObjects.idl
# generated code does not contain a copyright notice


# Import statements for member types

import rosidl_parser.definition  # noqa: E402, I100


class Metaclass_DetectObjects_Request(type):
    """Metaclass of message 'DetectObjects_Request'."""

    _CREATE_ROS_MESSAGE = None
    _CONVERT_FROM_PY = None
    _CONVERT_TO_PY = None
    _DESTROY_ROS_MESSAGE = None
    _TYPE_SUPPORT = None

    __constants = {
    }

    @classmethod
    def __import_type_support__(cls):
        try:
            from rosidl_generator_py import import_type_support
            module = import_type_support('object_detect_interface')
        except ImportError:
            import logging
            import traceback
            logger = logging.getLogger(
                'object_detect_interface.srv.DetectObjects_Request')
            logger.debug(
                'Failed to import needed modules for type support:\n' +
                traceback.format_exc())
        else:
            cls._CREATE_ROS_MESSAGE = module.create_ros_message_msg__srv__detect_objects__request
            cls._CONVERT_FROM_PY = module.convert_from_py_msg__srv__detect_objects__request
            cls._CONVERT_TO_PY = module.convert_to_py_msg__srv__detect_objects__request
            cls._TYPE_SUPPORT = module.type_support_msg__srv__detect_objects__request
            cls._DESTROY_ROS_MESSAGE = module.destroy_ros_message_msg__srv__detect_objects__request

    @classmethod
    def __prepare__(cls, name, bases, **kwargs):
        # list constant names here so that they appear in the help text of
        # the message class under "Data and other attributes defined here:"
        # as well as populate each message instance
        return {
        }


class DetectObjects_Request(metaclass=Metaclass_DetectObjects_Request):
    """Message class 'DetectObjects_Request'."""

    __slots__ = [
    ]

    _fields_and_field_types = {
    }

    SLOT_TYPES = (
    )

    def __init__(self, **kwargs):
        assert all('_' + key in self.__slots__ for key in kwargs.keys()), \
            'Invalid arguments passed to constructor: %s' % \
            ', '.join(sorted(k for k in kwargs.keys() if '_' + k not in self.__slots__))

    def __repr__(self):
        typename = self.__class__.__module__.split('.')
        typename.pop()
        typename.append(self.__class__.__name__)
        args = []
        for s, t in zip(self.__slots__, self.SLOT_TYPES):
            field = getattr(self, s)
            fieldstr = repr(field)
            # We use Python array type for fields that can be directly stored
            # in them, and "normal" sequences for everything else.  If it is
            # a type that we store in an array, strip off the 'array' portion.
            if (
                isinstance(t, rosidl_parser.definition.AbstractSequence) and
                isinstance(t.value_type, rosidl_parser.definition.BasicType) and
                t.value_type.typename in ['float', 'double', 'int8', 'uint8', 'int16', 'uint16', 'int32', 'uint32', 'int64', 'uint64']
            ):
                if len(field) == 0:
                    fieldstr = '[]'
                else:
                    assert fieldstr.startswith('array(')
                    prefix = "array('X', "
                    suffix = ')'
                    fieldstr = fieldstr[len(prefix):-len(suffix)]
            args.append(s[1:] + '=' + fieldstr)
        return '%s(%s)' % ('.'.join(typename), ', '.join(args))

    def __eq__(self, other):
        if not isinstance(other, self.__class__):
            return False
        return True

    @classmethod
    def get_fields_and_field_types(cls):
        from copy import copy
        return copy(cls._fields_and_field_types)


# Import statements for member types

import builtins  # noqa: E402, I100

# already imported above
# import rosidl_parser.definition


class Metaclass_DetectObjects_Response(type):
    """Metaclass of message 'DetectObjects_Response'."""

    _CREATE_ROS_MESSAGE = None
    _CONVERT_FROM_PY = None
    _CONVERT_TO_PY = None
    _DESTROY_ROS_MESSAGE = None
    _TYPE_SUPPORT = None

    __constants = {
    }

    @classmethod
    def __import_type_support__(cls):
        try:
            from rosidl_generator_py import import_type_support
            module = import_type_support('object_detect_interface')
        except ImportError:
            import logging
            import traceback
            logger = logging.getLogger(
                'object_detect_interface.srv.DetectObjects_Response')
            logger.debug(
                'Failed to import needed modules for type support:\n' +
                traceback.format_exc())
        else:
            cls._CREATE_ROS_MESSAGE = module.create_ros_message_msg__srv__detect_objects__response
            cls._CONVERT_FROM_PY = module.convert_from_py_msg__srv__detect_objects__response
            cls._CONVERT_TO_PY = module.convert_to_py_msg__srv__detect_objects__response
            cls._TYPE_SUPPORT = module.type_support_msg__srv__detect_objects__response
            cls._DESTROY_ROS_MESSAGE = module.destroy_ros_message_msg__srv__detect_objects__response

            from object_detect_interface.msg import ObjectData
            if ObjectData.__class__._TYPE_SUPPORT is None:
                ObjectData.__class__.__import_type_support__()

    @classmethod
    def __prepare__(cls, name, bases, **kwargs):
        # list constant names here so that they appear in the help text of
        # the message class under "Data and other attributes defined here:"
        # as well as populate each message instance
        return {
        }


class DetectObjects_Response(metaclass=Metaclass_DetectObjects_Response):
    """Message class 'DetectObjects_Response'."""

    __slots__ = [
        '_entity_num',
        '_object_list',
    ]

    _fields_and_field_types = {
        'entity_num': 'int16',
        'object_list': 'sequence<object_detect_interface/ObjectData>',
    }

    SLOT_TYPES = (
        rosidl_parser.definition.BasicType('int16'),  # noqa: E501
        rosidl_parser.definition.UnboundedSequence(rosidl_parser.definition.NamespacedType(['object_detect_interface', 'msg'], 'ObjectData')),  # noqa: E501
    )

    def __init__(self, **kwargs):
        assert all('_' + key in self.__slots__ for key in kwargs.keys()), \
            'Invalid arguments passed to constructor: %s' % \
            ', '.join(sorted(k for k in kwargs.keys() if '_' + k not in self.__slots__))
        self.entity_num = kwargs.get('entity_num', int())
        self.object_list = kwargs.get('object_list', [])

    def __repr__(self):
        typename = self.__class__.__module__.split('.')
        typename.pop()
        typename.append(self.__class__.__name__)
        args = []
        for s, t in zip(self.__slots__, self.SLOT_TYPES):
            field = getattr(self, s)
            fieldstr = repr(field)
            # We use Python array type for fields that can be directly stored
            # in them, and "normal" sequences for everything else.  If it is
            # a type that we store in an array, strip off the 'array' portion.
            if (
                isinstance(t, rosidl_parser.definition.AbstractSequence) and
                isinstance(t.value_type, rosidl_parser.definition.BasicType) and
                t.value_type.typename in ['float', 'double', 'int8', 'uint8', 'int16', 'uint16', 'int32', 'uint32', 'int64', 'uint64']
            ):
                if len(field) == 0:
                    fieldstr = '[]'
                else:
                    assert fieldstr.startswith('array(')
                    prefix = "array('X', "
                    suffix = ')'
                    fieldstr = fieldstr[len(prefix):-len(suffix)]
            args.append(s[1:] + '=' + fieldstr)
        return '%s(%s)' % ('.'.join(typename), ', '.join(args))

    def __eq__(self, other):
        if not isinstance(other, self.__class__):
            return False
        if self.entity_num != other.entity_num:
            return False
        if self.object_list != other.object_list:
            return False
        return True

    @classmethod
    def get_fields_and_field_types(cls):
        from copy import copy
        return copy(cls._fields_and_field_types)

    @builtins.property
    def entity_num(self):
        """Message field 'entity_num'."""
        return self._entity_num

    @entity_num.setter
    def entity_num(self, value):
        if __debug__:
            assert \
                isinstance(value, int), \
                "The 'entity_num' field must be of type 'int'"
            assert value >= -32768 and value < 32768, \
                "The 'entity_num' field must be an integer in [-32768, 32767]"
        self._entity_num = value

    @builtins.property
    def object_list(self):
        """Message field 'object_list'."""
        return self._object_list

    @object_list.setter
    def object_list(self, value):
        if __debug__:
            from object_detect_interface.msg import ObjectData
            from collections.abc import Sequence
            from collections.abc import Set
            from collections import UserList
            from collections import UserString
            assert \
                ((isinstance(value, Sequence) or
                  isinstance(value, Set) or
                  isinstance(value, UserList)) and
                 not isinstance(value, str) and
                 not isinstance(value, UserString) and
                 all(isinstance(v, ObjectData) for v in value) and
                 True), \
                "The 'object_list' field must be a set or sequence and each value of type 'ObjectData'"
        self._object_list = value


class Metaclass_DetectObjects(type):
    """Metaclass of service 'DetectObjects'."""

    _TYPE_SUPPORT = None

    @classmethod
    def __import_type_support__(cls):
        try:
            from rosidl_generator_py import import_type_support
            module = import_type_support('object_detect_interface')
        except ImportError:
            import logging
            import traceback
            logger = logging.getLogger(
                'object_detect_interface.srv.DetectObjects')
            logger.debug(
                'Failed to import needed modules for type support:\n' +
                traceback.format_exc())
        else:
            cls._TYPE_SUPPORT = module.type_support_srv__srv__detect_objects

            from object_detect_interface.srv import _detect_objects
            if _detect_objects.Metaclass_DetectObjects_Request._TYPE_SUPPORT is None:
                _detect_objects.Metaclass_DetectObjects_Request.__import_type_support__()
            if _detect_objects.Metaclass_DetectObjects_Response._TYPE_SUPPORT is None:
                _detect_objects.Metaclass_DetectObjects_Response.__import_type_support__()


class DetectObjects(metaclass=Metaclass_DetectObjects):
    from object_detect_interface.srv._detect_objects import DetectObjects_Request as Request
    from object_detect_interface.srv._detect_objects import DetectObjects_Response as Response

    def __init__(self):
        raise NotImplementedError('Service classes can not be instantiated')
