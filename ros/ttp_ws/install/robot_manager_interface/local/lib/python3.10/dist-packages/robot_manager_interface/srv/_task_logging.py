# generated from rosidl_generator_py/resource/_idl.py.em
# with input from robot_manager_interface:srv/TaskLogging.idl
# generated code does not contain a copyright notice


# Import statements for member types

import builtins  # noqa: E402, I100

import rosidl_parser.definition  # noqa: E402, I100


class Metaclass_TaskLogging_Request(type):
    """Metaclass of message 'TaskLogging_Request'."""

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
            module = import_type_support('robot_manager_interface')
        except ImportError:
            import logging
            import traceback
            logger = logging.getLogger(
                'robot_manager_interface.srv.TaskLogging_Request')
            logger.debug(
                'Failed to import needed modules for type support:\n' +
                traceback.format_exc())
        else:
            cls._CREATE_ROS_MESSAGE = module.create_ros_message_msg__srv__task_logging__request
            cls._CONVERT_FROM_PY = module.convert_from_py_msg__srv__task_logging__request
            cls._CONVERT_TO_PY = module.convert_to_py_msg__srv__task_logging__request
            cls._TYPE_SUPPORT = module.type_support_msg__srv__task_logging__request
            cls._DESTROY_ROS_MESSAGE = module.destroy_ros_message_msg__srv__task_logging__request

    @classmethod
    def __prepare__(cls, name, bases, **kwargs):
        # list constant names here so that they appear in the help text of
        # the message class under "Data and other attributes defined here:"
        # as well as populate each message instance
        return {
            'SEQUENCE_ID__DEFAULT': -1,
            'SUB_ACTION__DEFAULT': 'move',
            'RELATIVITY__DEFAULT': False,
        }

    @property
    def SEQUENCE_ID__DEFAULT(cls):
        """Return default value for message field 'sequence_id'."""
        return -1

    @property
    def SUB_ACTION__DEFAULT(cls):
        """Return default value for message field 'sub_action'."""
        return 'move'

    @property
    def RELATIVITY__DEFAULT(cls):
        """Return default value for message field 'relativity'."""
        return False


class TaskLogging_Request(metaclass=Metaclass_TaskLogging_Request):
    """Message class 'TaskLogging_Request'."""

    __slots__ = [
        '_object_id_a',
        '_object_id_b',
        '_instruction',
        '_sequence_id',
        '_sub_action',
        '_relativity',
    ]

    _fields_and_field_types = {
        'object_id_a': 'int16',
        'object_id_b': 'int16',
        'instruction': 'int16',
        'sequence_id': 'int16',
        'sub_action': 'string',
        'relativity': 'boolean',
    }

    SLOT_TYPES = (
        rosidl_parser.definition.BasicType('int16'),  # noqa: E501
        rosidl_parser.definition.BasicType('int16'),  # noqa: E501
        rosidl_parser.definition.BasicType('int16'),  # noqa: E501
        rosidl_parser.definition.BasicType('int16'),  # noqa: E501
        rosidl_parser.definition.UnboundedString(),  # noqa: E501
        rosidl_parser.definition.BasicType('boolean'),  # noqa: E501
    )

    def __init__(self, **kwargs):
        assert all('_' + key in self.__slots__ for key in kwargs.keys()), \
            'Invalid arguments passed to constructor: %s' % \
            ', '.join(sorted(k for k in kwargs.keys() if '_' + k not in self.__slots__))
        self.object_id_a = kwargs.get('object_id_a', int())
        self.object_id_b = kwargs.get('object_id_b', int())
        self.instruction = kwargs.get('instruction', int())
        self.sequence_id = kwargs.get(
            'sequence_id', TaskLogging_Request.SEQUENCE_ID__DEFAULT)
        self.sub_action = kwargs.get(
            'sub_action', TaskLogging_Request.SUB_ACTION__DEFAULT)
        self.relativity = kwargs.get(
            'relativity', TaskLogging_Request.RELATIVITY__DEFAULT)

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
        if self.object_id_a != other.object_id_a:
            return False
        if self.object_id_b != other.object_id_b:
            return False
        if self.instruction != other.instruction:
            return False
        if self.sequence_id != other.sequence_id:
            return False
        if self.sub_action != other.sub_action:
            return False
        if self.relativity != other.relativity:
            return False
        return True

    @classmethod
    def get_fields_and_field_types(cls):
        from copy import copy
        return copy(cls._fields_and_field_types)

    @builtins.property
    def object_id_a(self):
        """Message field 'object_id_a'."""
        return self._object_id_a

    @object_id_a.setter
    def object_id_a(self, value):
        if __debug__:
            assert \
                isinstance(value, int), \
                "The 'object_id_a' field must be of type 'int'"
            assert value >= -32768 and value < 32768, \
                "The 'object_id_a' field must be an integer in [-32768, 32767]"
        self._object_id_a = value

    @builtins.property
    def object_id_b(self):
        """Message field 'object_id_b'."""
        return self._object_id_b

    @object_id_b.setter
    def object_id_b(self, value):
        if __debug__:
            assert \
                isinstance(value, int), \
                "The 'object_id_b' field must be of type 'int'"
            assert value >= -32768 and value < 32768, \
                "The 'object_id_b' field must be an integer in [-32768, 32767]"
        self._object_id_b = value

    @builtins.property
    def instruction(self):
        """Message field 'instruction'."""
        return self._instruction

    @instruction.setter
    def instruction(self, value):
        if __debug__:
            assert \
                isinstance(value, int), \
                "The 'instruction' field must be of type 'int'"
            assert value >= -32768 and value < 32768, \
                "The 'instruction' field must be an integer in [-32768, 32767]"
        self._instruction = value

    @builtins.property
    def sequence_id(self):
        """Message field 'sequence_id'."""
        return self._sequence_id

    @sequence_id.setter
    def sequence_id(self, value):
        if __debug__:
            assert \
                isinstance(value, int), \
                "The 'sequence_id' field must be of type 'int'"
            assert value >= -32768 and value < 32768, \
                "The 'sequence_id' field must be an integer in [-32768, 32767]"
        self._sequence_id = value

    @builtins.property
    def sub_action(self):
        """Message field 'sub_action'."""
        return self._sub_action

    @sub_action.setter
    def sub_action(self, value):
        if __debug__:
            assert \
                isinstance(value, str), \
                "The 'sub_action' field must be of type 'str'"
        self._sub_action = value

    @builtins.property
    def relativity(self):
        """Message field 'relativity'."""
        return self._relativity

    @relativity.setter
    def relativity(self, value):
        if __debug__:
            assert \
                isinstance(value, bool), \
                "The 'relativity' field must be of type 'bool'"
        self._relativity = value


# Import statements for member types

# already imported above
# import builtins

# already imported above
# import rosidl_parser.definition


class Metaclass_TaskLogging_Response(type):
    """Metaclass of message 'TaskLogging_Response'."""

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
            module = import_type_support('robot_manager_interface')
        except ImportError:
            import logging
            import traceback
            logger = logging.getLogger(
                'robot_manager_interface.srv.TaskLogging_Response')
            logger.debug(
                'Failed to import needed modules for type support:\n' +
                traceback.format_exc())
        else:
            cls._CREATE_ROS_MESSAGE = module.create_ros_message_msg__srv__task_logging__response
            cls._CONVERT_FROM_PY = module.convert_from_py_msg__srv__task_logging__response
            cls._CONVERT_TO_PY = module.convert_to_py_msg__srv__task_logging__response
            cls._TYPE_SUPPORT = module.type_support_msg__srv__task_logging__response
            cls._DESTROY_ROS_MESSAGE = module.destroy_ros_message_msg__srv__task_logging__response

    @classmethod
    def __prepare__(cls, name, bases, **kwargs):
        # list constant names here so that they appear in the help text of
        # the message class under "Data and other attributes defined here:"
        # as well as populate each message instance
        return {
        }


class TaskLogging_Response(metaclass=Metaclass_TaskLogging_Response):
    """Message class 'TaskLogging_Response'."""

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


class Metaclass_TaskLogging(type):
    """Metaclass of service 'TaskLogging'."""

    _TYPE_SUPPORT = None

    @classmethod
    def __import_type_support__(cls):
        try:
            from rosidl_generator_py import import_type_support
            module = import_type_support('robot_manager_interface')
        except ImportError:
            import logging
            import traceback
            logger = logging.getLogger(
                'robot_manager_interface.srv.TaskLogging')
            logger.debug(
                'Failed to import needed modules for type support:\n' +
                traceback.format_exc())
        else:
            cls._TYPE_SUPPORT = module.type_support_srv__srv__task_logging

            from robot_manager_interface.srv import _task_logging
            if _task_logging.Metaclass_TaskLogging_Request._TYPE_SUPPORT is None:
                _task_logging.Metaclass_TaskLogging_Request.__import_type_support__()
            if _task_logging.Metaclass_TaskLogging_Response._TYPE_SUPPORT is None:
                _task_logging.Metaclass_TaskLogging_Response.__import_type_support__()


class TaskLogging(metaclass=Metaclass_TaskLogging):
    from robot_manager_interface.srv._task_logging import TaskLogging_Request as Request
    from robot_manager_interface.srv._task_logging import TaskLogging_Response as Response

    def __init__(self):
        raise NotImplementedError('Service classes can not be instantiated')
