//기본 라이브러리
#include "iostream"
#include "string"

//외부 라이브러리
// #include <modbus.h>
#include <modbus/modbus.h>

//ros2 라이브러리
#include "rclcpp/rclcpp.hpp"
#include "rclcpp/duration.hpp"
#include "rclcpp_components/register_node_macro.hpp"

//ros2 interface
#include "robotiq_gripper_interface/srv/set_gripper_state_command.hpp"
#include "robotiq_gripper_interface/srv/get_gripper_state_command.hpp"
#include "robotiq_gripper_interface/msg/gripper_state.hpp"
// #include "sensor_msgs/JointState.h"

using namespace std;


class RobotiqGripper : public rclcpp::Node
{
public:
	using Gripperstatemsg = robotiq_gripper_interface::msg::GripperState;
	// using JointStatemsg = sensor_msgs::msg::JointState;
	using SetGripper = robotiq_gripper_interface::srv::SetGripperStateCommand;
	using GetGripper = robotiq_gripper_interface::srv::GetGripperStateCommand;
	

	explicit __attribute__ ((visibility("default"))) RobotiqGripper(const rclcpp::NodeOptions & node_options = rclcpp::NodeOptions().automatically_declare_parameters_from_overrides(true));
	// explicit __attribute__ ((visibility("default"))) MoveitProxyServer(const rclcpp::NodeOptions & node_options = rclcpp::NodeOptions());
	virtual ~RobotiqGripper();

private:
	rclcpp::Service<SetGripper>::SharedPtr set_gripper_server_ptr = nullptr;
	rclcpp::Service<GetGripper>::SharedPtr get_gripper_server_ptr = nullptr;

	rclcpp::Publisher<Gripperstatemsg>::SharedPtr gripper_state_publisher_ptr = nullptr;
	// rclcpp::Publisher<JointStatemsg>::SharedPtr gripper_joint_state_publisher_ptr = nullptr;
	
	rclcpp::TimerBase::SharedPtr control_comunication_timer_ptr = nullptr;

	modbus_t* modbus_instance = nullptr;

	//상태 변수 선언
	uint8_t req_gripper_pos = 0;
	uint8_t req_gripper_speed = 0;
	uint8_t req_gripper_force = 0;

	void callback_set_gripper_state(const std::shared_ptr<rmw_request_id_t> request_header, const std::shared_ptr<SetGripper::Request> request, std::shared_ptr<SetGripper::Response> response);
	void callback_get_gripper_state(const std::shared_ptr<rmw_request_id_t> request_header, const std::shared_ptr<GetGripper::Request> request, std::shared_ptr<GetGripper::Response> response);
	void callback_control_comunication_timer();

};
