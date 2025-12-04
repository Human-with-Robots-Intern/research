#include "iostream"



#include "rclcpp/rclcpp.hpp"
#include "rclcpp_components/register_node_macro.hpp"

#include "robotiq_gripper_interface/srv/gripper_state.hpp"
#include "robotiq_gripper_interface/srv/gripper_command.hpp"


using namespace std;


class RobotiqGripper : public rclcpp::Node
{
public:
	using GripperState = robotiq_gripper_interface::srv::GripperState;
	using GripperCommand = robotiq_gripper_interface::srv::GripperCommand;

	explicit __attribute__ ((visibility("default"))) RobotiqGripper(const rclcpp::NodeOptions & node_options = rclcpp::NodeOptions().automatically_declare_parameters_from_overrides(true));
	// explicit __attribute__ ((visibility("default"))) MoveitProxyServer(const rclcpp::NodeOptions & node_options = rclcpp::NodeOptions());
	virtual ~RobotiqGripper();

private:
	rclcpp::Service<GripperState>::SharedPtr GripperState_server_ptr;
	rclcpp::Service<GripperCommand>::SharedPtr GripperCommand_server_ptr;	
	rclcpp::TimerBase::SharedPtr state_publish_timer;

	void callback_reply_state(const std::shared_ptr<rmw_request_id_t> request_header, const std::shared_ptr<GripperState::Request> request, std::shared_ptr<GripperState::Response> response);
	void callback_gripper_move(const std::shared_ptr<rmw_request_id_t> request_header, const std::shared_ptr<GripperCommand::Request> request, std::shared_ptr<GripperCommand::Response> response);


};
