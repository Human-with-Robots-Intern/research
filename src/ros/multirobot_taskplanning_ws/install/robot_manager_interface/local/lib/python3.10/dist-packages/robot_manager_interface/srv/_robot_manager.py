# generated from rosidl_generator_py/resource/_idl.py.em
# with input from robot_manager_interface:srv/RobotManager.idl
# generated code does not contain a copyright notice


# Import statements for member types

import builtins  # noqa: E402, I100

import rosidl_parser.definition  # noqa: E402, I100


class Metaclass_RobotManager_Request(type):
    """Metaclass of message 'RobotManager_Request'."""

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
                'robot_manager_interface.srv.RobotManager_Request')
            logger.debug(
                'Failed to import needed modules for type support:\n' +
                traceback.format_exc())
        else:
            cls._CREATE_ROS_MESSAGE = module.create_ros_message_msg__srv__robot_manager__request
            cls._CONVERT_FROM_PY = module.convert_from_py_msg__srv__robot_manager__request
            cls._CONVERT_TO_PY = module.convert_to_py_msg__srv__robot_manager__request
            cls._TYPE_SUPPORT = module.type_support_msg__srv__robot_manager__request
            cls._DESTROY_ROS_MESSAGE = module.destroy_ros_message_msg__srv__robot_manager__request

    @classmethod
    def __prepare__(cls, name, bases, **kwargs):
        # list constant names here so that they appear in the help text of
        # the message class under "Data and other attributes defined here:"
        # as well as populate each message instance
        return {
        }


class RobotManager_Request(metaclass=Metaclass_RobotManager_Request):
    """Message class 'RobotManager_Request'."""

    __slots__ = [
        '_robot_model',
        '_instruction',
        '_a',
        '_b',
    ]

    _fields_and_field_types = {
        'robot_model': 'int64',
        'instruction': 'int64',
        'a': 'int64',
        'b': 'int64',
    }

    SLOT_TYPES = (
        rosidl_parser.definition.BasicType('int64'),  # noqa: E501
        rosidl_parser.definition.BasicType('int64'),  # noqa: E501
        rosidl_parser.definition.BasicType('int64'),  # noqa: E501
        rosidl_parser.definition.BasicType('int64'),  # noqa: E501
    )

    def __init__(self, **kwargs):
        assert all('_' + key in self.__slots__ for key in kwargs.keys()), \
            'Invalid arguments passed to constructor: %s' % \
            ', '.join(sorted(k for k in kwargs.keys() if '_' + k not in self.__slots__))
        self.robot_model = kwargs.get('robot_model', int())
        self.instruction = kwargs.get('instruction', int())
        self.a = kwargs.get('a', int())
        self.b = kwargs.get('b', int())

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
        if self.robot_model != other.robot_model:
            return False
        if self.instruction != other.instruction:
            return False
        if self.a != other.a:
            return False
        if self.b != other.b:
            return False
        return True

    @classmethod
    def get_fields_and_field_types(cls):
        from copy import copy
        return copy(cls._fields_and_field_types)

    @builtins.property
    def robot_model(self):
        """Message field 'robot_model'."""
        return self._robot_model

    @robot_model.setter
    def robot_model(self, value):
        if __debug__:
            assert \
                isinstance(value, int), \
                "The 'robot_model' field must be of type 'int'"
            assert value >= -9223372036854775808 and value < 9223372036854775808, \
                "The 'robot_model' field must be an integer in [-9223372036854775808, 9223372036854775807]"
        self._robot_model = value

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
            assert value >= -9223372036854775808 and value < 9223372036854775808, \
                "The 'instruction' field must be an integer in [-9223372036854775808, 9223372036854775807]"
        self._instruction = value

    @builtins.property
    def a(self):
        """Message field 'a'."""
        return self._a

    @a.setter
    def a(self, value):
        if __debug__:
            assert \
                isinstance(value, int), \
                "The 'a' field must be of type 'int'"
            assert value >= -9223372036854775808 and value < 9223372036854775808, \
                "The 'a' field must be an integer in [-9223372036854775808, 9223372036854775807]"
        self._a = value

    @builtins.property
    def b(self):
        """Message field 'b'."""
        return self._b

    @b.setter
    def b(self, value):
        if __debug__:
            assert \
                isinstance(value, int), \
                "The 'b' field must be of type 'int'"
            assert value >= -9223372036854775808 and value < 9223372036854775808, \
                "The 'b' field must be an integer in [-9223372036854775808, 9223372036854775807]"
        self._b = value


# Import statements for member types

# already imported above
# import builtins

# already imported above
# import rosidl_parser.definition


class Metaclass_RobotManager_Response(type):
    """Metaclass of message 'RobotManager_Response'."""

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
                'robot_manager_interface.srv.RobotManager_Response')
            logger.debug(
                'Failed to import needed modules for type support:\n' +
                traceback.format_exc())
        else:
            cls._CREATE_ROS_MESSAGE = module.create_ros_message_msg__srv__robot_manager__response
            cls._CONVERT_FROM_PY = module.convert_from_py_msg__srv__robot_manager__response
            cls._CONVERT_TO_PY = module.convert_to_py_msg__srv__robot_manager__response
            cls._TYPE_SUPPORT = module.type_support_msg__srv__robot_manager__response
            cls._DESTROY_ROS_MESSAGE = module.destroy_ros_message_msg__srv__robot_manager__response

    @classmethod
    def __prepare__(cls, name, bases, **kwargs):
        # list constant names here so that they appear in the help text of
        # the message class under "Data and other attributes defined here:"
        # as well as populate each message instance
        return {
        }


class RobotManager_Response(metaclass=Metaclass_RobotManager_Response):
    """Message class 'RobotManager_Response'."""

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


class Metaclass_RobotManager(type):
    """Metaclass of service 'RobotManager'."""

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
                'robot_manager_interface.srv.RobotManager')
            logger.debug(
                'Failed to import needed modules for type support:\n' +
                traceback.format_exc())
        else:
            cls._TYPE_SUPPORT = module.type_support_srv__srv__robot_manager

            from robot_manager_interface.srv import _robot_manager
            if _robot_manager.Metaclass_RobotManager_Request._TYPE_SUPPORT is None:
                _robot_manager.Metaclass_RobotManager_Request.__import_type_support__()
            if _robot_manager.Metaclass_RobotManager_Response._TYPE_SUPPORT is None:
                _robot_manager.Metaclass_RobotManager_Response.__import_type_support__()


class RobotManager(metaclass=Metaclass_RobotManager):
    from robot_manager_interface.srv._robot_manager import RobotManager_Request as Request
    from robot_manager_interface.srv._robot_manager import RobotManager_Response as Response

    def __init__(self):
        raise NotImplementedError('Service classes can not be instantiated')
