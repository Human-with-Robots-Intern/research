# generated from rosidl_generator_py/resource/_idl.py.em
# with input from manipulation_interface:srv/InitLogging.idl
# generated code does not contain a copyright notice


# Import statements for member types

import builtins  # noqa: E402, I100

import rosidl_parser.definition  # noqa: E402, I100


class Metaclass_InitLogging_Request(type):
    """Metaclass of message 'InitLogging_Request'."""

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
            module = import_type_support('manipulation_interface')
        except ImportError:
            import logging
            import traceback
            logger = logging.getLogger(
                'manipulation_interface.srv.InitLogging_Request')
            logger.debug(
                'Failed to import needed modules for type support:\n' +
                traceback.format_exc())
        else:
            cls._CREATE_ROS_MESSAGE = module.create_ros_message_msg__srv__init_logging__request
            cls._CONVERT_FROM_PY = module.convert_from_py_msg__srv__init_logging__request
            cls._CONVERT_TO_PY = module.convert_to_py_msg__srv__init_logging__request
            cls._TYPE_SUPPORT = module.type_support_msg__srv__init_logging__request
            cls._DESTROY_ROS_MESSAGE = module.destroy_ros_message_msg__srv__init_logging__request

    @classmethod
    def __prepare__(cls, name, bases, **kwargs):
        # list constant names here so that they appear in the help text of
        # the message class under "Data and other attributes defined here:"
        # as well as populate each message instance
        return {
        }


class InitLogging_Request(metaclass=Metaclass_InitLogging_Request):
    """Message class 'InitLogging_Request'."""

    __slots__ = [
        '_object_id',
        '_action_id',
    ]

    _fields_and_field_types = {
        'object_id': 'int16',
        'action_id': 'int16',
    }

    SLOT_TYPES = (
        rosidl_parser.definition.BasicType('int16'),  # noqa: E501
        rosidl_parser.definition.BasicType('int16'),  # noqa: E501
    )

    def __init__(self, **kwargs):
        assert all('_' + key in self.__slots__ for key in kwargs.keys()), \
            'Invalid arguments passed to constructor: %s' % \
            ', '.join(sorted(k for k in kwargs.keys() if '_' + k not in self.__slots__))
        self.object_id = kwargs.get('object_id', int())
        self.action_id = kwargs.get('action_id', int())

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
        if self.object_id != other.object_id:
            return False
        if self.action_id != other.action_id:
            return False
        return True

    @classmethod
    def get_fields_and_field_types(cls):
        from copy import copy
        return copy(cls._fields_and_field_types)

    @builtins.property
    def object_id(self):
        """Message field 'object_id'."""
        return self._object_id

    @object_id.setter
    def object_id(self, value):
        if __debug__:
            assert \
                isinstance(value, int), \
                "The 'object_id' field must be of type 'int'"
            assert value >= -32768 and value < 32768, \
                "The 'object_id' field must be an integer in [-32768, 32767]"
        self._object_id = value

    @builtins.property
    def action_id(self):
        """Message field 'action_id'."""
        return self._action_id

    @action_id.setter
    def action_id(self, value):
        if __debug__:
            assert \
                isinstance(value, int), \
                "The 'action_id' field must be of type 'int'"
            assert value >= -32768 and value < 32768, \
                "The 'action_id' field must be an integer in [-32768, 32767]"
        self._action_id = value


# Import statements for member types

# already imported above
# import builtins

# already imported above
# import rosidl_parser.definition


class Metaclass_InitLogging_Response(type):
    """Metaclass of message 'InitLogging_Response'."""

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
            module = import_type_support('manipulation_interface')
        except ImportError:
            import logging
            import traceback
            logger = logging.getLogger(
                'manipulation_interface.srv.InitLogging_Response')
            logger.debug(
                'Failed to import needed modules for type support:\n' +
                traceback.format_exc())
        else:
            cls._CREATE_ROS_MESSAGE = module.create_ros_message_msg__srv__init_logging__response
            cls._CONVERT_FROM_PY = module.convert_from_py_msg__srv__init_logging__response
            cls._CONVERT_TO_PY = module.convert_to_py_msg__srv__init_logging__response
            cls._TYPE_SUPPORT = module.type_support_msg__srv__init_logging__response
            cls._DESTROY_ROS_MESSAGE = module.destroy_ros_message_msg__srv__init_logging__response

    @classmethod
    def __prepare__(cls, name, bases, **kwargs):
        # list constant names here so that they appear in the help text of
        # the message class under "Data and other attributes defined here:"
        # as well as populate each message instance
        return {
        }


class InitLogging_Response(metaclass=Metaclass_InitLogging_Response):
    """Message class 'InitLogging_Response'."""

    __slots__ = [
        '_success',
    ]

    _fields_and_field_types = {
        'success': 'boolean',
    }

    SLOT_TYPES = (
        rosidl_parser.definition.BasicType('boolean'),  # noqa: E501
    )

    def __init__(self, **kwargs):
        assert all('_' + key in self.__slots__ for key in kwargs.keys()), \
            'Invalid arguments passed to constructor: %s' % \
            ', '.join(sorted(k for k in kwargs.keys() if '_' + k not in self.__slots__))
        self.success = kwargs.get('success', bool())

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
        if self.success != other.success:
            return False
        return True

    @classmethod
    def get_fields_and_field_types(cls):
        from copy import copy
        return copy(cls._fields_and_field_types)

    @builtins.property
    def success(self):
        """Message field 'success'."""
        return self._success

    @success.setter
    def success(self, value):
        if __debug__:
            assert \
                isinstance(value, bool), \
                "The 'success' field must be of type 'bool'"
        self._success = value


class Metaclass_InitLogging(type):
    """Metaclass of service 'InitLogging'."""

    _TYPE_SUPPORT = None

    @classmethod
    def __import_type_support__(cls):
        try:
            from rosidl_generator_py import import_type_support
            module = import_type_support('manipulation_interface')
        except ImportError:
            import logging
            import traceback
            logger = logging.getLogger(
                'manipulation_interface.srv.InitLogging')
            logger.debug(
                'Failed to import needed modules for type support:\n' +
                traceback.format_exc())
        else:
            cls._TYPE_SUPPORT = module.type_support_srv__srv__init_logging

            from manipulation_interface.srv import _init_logging
            if _init_logging.Metaclass_InitLogging_Request._TYPE_SUPPORT is None:
                _init_logging.Metaclass_InitLogging_Request.__import_type_support__()
            if _init_logging.Metaclass_InitLogging_Response._TYPE_SUPPORT is None:
                _init_logging.Metaclass_InitLogging_Response.__import_type_support__()


class InitLogging(metaclass=Metaclass_InitLogging):
    from manipulation_interface.srv._init_logging import InitLogging_Request as Request
    from manipulation_interface.srv._init_logging import InitLogging_Response as Response

    def __init__(self):
        raise NotImplementedError('Service classes can not be instantiated')
