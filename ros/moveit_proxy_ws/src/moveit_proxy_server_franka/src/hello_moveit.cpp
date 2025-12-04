#include <memory>
#include <iostream>

#include <rclcpp/rclcpp.hpp>
#include <moveit/move_group_interface/move_group_interface.h>


void MoveitProxyServer::do_plan([[maybe_unused]] const std::shared_ptr<rmw_request_id_t> request_header, const std::shared_ptr<SendPlan::Request> request, std::shared_ptr<SendPlan::Response> response)
{
	std::cout<<"test_do_plan"<<std::endl;
	std::cout<<(*request).goal_pose.position.x<<std::endl;
	std::cout<<(*request).goal_pose.position.y<<std::endl;
	std::cout<<(*request).goal_pose.position.z<<std::endl;
	
	// 멤버 함수 테스트 std::cout<<private_memver_var<<std::endl;
	
	// move_group_interface_instance.setPoseTarget((*request).goal_pose);
    // plan_success = static_cast<bool>(move_group_interface_instance.plan(plan_instance));//msg가 & 참조 변수로 작용하여 함수 호출이후 덮어쓰기 됨에 주의
	
	// if(plan_success == true)
	if(1 == true)
	{
		(*response).result = true;//boolean
	}
	else
	{
		(*response).result = false;//boolean
		RCLCPP_ERROR(this->get_logger(), "Planing failed!");
	}
	std::cout<<"test_do_plan_finished"<<std::endl;
}

void do_exec([[maybe_unused]] const std::shared_ptr<rmw_request_id_t> request_header, [[maybe_unused]] const std::shared_ptr<ExecPlan::Request> request, std::shared_ptr<ExecPlan::Response> response)
{
	//[[maybe_unused]] 변수를 사용하지 않아도 오류를 내지 않도록 하는 매크로, c++17 이상에서 지원
	std::cout<<"test_do_exec"<<std::endl;
	// rclcpp::sleep_for(std::chrono::seconds(3));//테스트용 시간 지연
	// if(plan_success == true) {
	if(1 == true) {
    	// move_group_interface_instance.execute(plan_instance);
		(*response).result = true;//boolean
	}
	else
	{
		RCLCPP_ERROR(this->get_logger(), "Executing failed!");
		(*response).result = false;//boolean
	}
	std::cout<<"test_do_exec_finished"<<std::endl;
}



int main(int argc, char * argv[])
{
  // Initialize ROS and create the Node
  rclcpp::init(argc, argv);
  auto const node = std::make_shared<rclcpp::Node>(
    "hello_moveit",
    rclcpp::NodeOptions().automatically_declare_parameters_from_overrides(true)
  );

  // Create a ROS logger
  auto const logger = rclcpp::get_logger("hello_moveit");
  // Next step goes here
  // Create the MoveIt MoveGroup Interface
  using moveit::planning_interface::MoveGroupInterface;
  // moveit::planning_interface::MoveGroupInterface::Options opt("panda_arm", "config/panda.urdf.xacro", "");

  std::cout << "hello_moveit_panda_00_panda_arm" << std::endl; 
  // auto move_group_interface = MoveGroupInterface(node, opt);
  // std::cout << "hello_moveit_panda_01" << std::endl; 
  auto move_group_interface = MoveGroupInterface(node, "panda_arm");
  std::cout << "hello_moveit_panda_01" << std::endl; 
  // auto move_group_interface = MoveGroupInterface(node, "panda_robot");
  // std::cout << "hello_moveit_panda_00" << std::endl; 
  // auto move_group_interface = MoveGroupInterface(node, "panda_manipulator");
  // std::cout << "panda_manipulator" << std::endl; 
  // auto move_group_interface = MoveGroupInterface(node, "panda_arm_hand");
  // std::cout << "panda_arm_hand" << std::endl; 
  // auto move_group_interface = MoveGroupInterface(node, "rabbit_arm");
  // std::cout << "hello_moveit_rabbit_00" << std::endl; 

  // Set a target Pose
  auto const target_pose = []{
    geometry_msgs::msg::Pose msg;
    msg.orientation.w = 1.0;
    msg.position.x = 0.28;
    msg.position.y = -0.2;
    msg.position.z = 0.5;
    return msg;
  }();
  move_group_interface.setPoseTarget(target_pose);

  // Create a plan to that target pose
  auto const [success, plan] = [&move_group_interface]{
    moveit::planning_interface::MoveGroupInterface::Plan msg;
    auto const ok = static_cast<bool>(move_group_interface.plan(msg));
    return std::make_pair(ok, msg);
  }();

  // Execute the plan
  if(success) {
    move_group_interface.execute(plan);
  } else {
    RCLCPP_ERROR(logger, "Planing failed!");
  }
  // Shutdown ROS
  rclcpp::shutdown();
  return 0;
}
