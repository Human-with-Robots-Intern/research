#include "robotiq_gripper.hpp"

RobotiqGripper::RobotiqGripper(const rclcpp::NodeOptions & node_options /*= rclcpp::NodeOptions()*/)
: Node("moveit_proxy_server", node_options)
{

}

RobotiqGripper::~RobotiqGripper()
{
    
}

void RobotiqGripper::callback_reply_state(const std::shared_ptr<rmw_request_id_t> request_header, const std::shared_ptr<GripperState::Request> request, std::shared_ptr<GripperState::Response> response)
{

}

void RobotiqGripper::callback_gripper_move(const std::shared_ptr<rmw_request_id_t> request_header, const std::shared_ptr<GripperCommand::Request> request, std::shared_ptr<GripperCommand::Response> response)
{

}

RCLCPP_COMPONENTS_REGISTER_NODE(RobotiqGripper)
