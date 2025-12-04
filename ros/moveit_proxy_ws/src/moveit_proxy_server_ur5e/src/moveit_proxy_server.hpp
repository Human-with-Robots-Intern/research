#ifndef MOVEI_PROXY_SERVER
#define MOVEI_PROXY_SERVER


#include "iostream"
#include "string"
#include "utility"
#include "rclcpp/rclcpp.hpp"

// #include "visibility_control.hpp"
#include <moveit/move_group_interface/move_group_interface.h>
#include "rclcpp_components/register_node_macro.hpp"
//#include "rclcpp_components/register_node_macro.hpp"//main 함수 없이도 노드를 사용할 수 있도록 도와주는 macro 인듯 하다

#include "moveit_proxy_interface/srv/send_plan.hpp"
#include "moveit_proxy_interface/srv/exec_plan.hpp"
// interface의 이름이 결정될 때 소스이름 상의 camel case를 빌드 후에는 자동으로 "_" 간격으로 바꿔주는 기능이 있어 헷갈림에 주의 
// https://docs.ros.org/en/humble/Tutorials/Beginner-Client-Libraries/Single-Package-Define-And-Use-Interface.html#use-an-interface-from-the-same-package
// 위 링크의 소스코드에서도 동일한 현상 확인 가능

using namespace std;

//moveit 용 내임스페이스
using moveit::planning_interface::MoveGroupInterface;

class MoveitProxyServer : public rclcpp::Node
{
public:
	//네임스페이스 상에서는 camel case 그대로 부른다.(주의...)
	using SendPlan = moveit_proxy_interface::srv::SendPlan;
	using ExecPlan = moveit_proxy_interface::srv::ExecPlan;

	//shared_from_this() 
	// https://en.cppreference.com/w/cpp/memory/enable_shared_from_this/shared_from_this
	// node 객체는 구현 시부터
	// std::enable_shared_from_this<> 를 상속받아서 만들어 졌다고 볼 수 있다.


    // 클래스 생성자를 동적 라이브러리에서 사용할 수 있도록 visibility 정의
	
	explicit __attribute__ ((visibility("default"))) MoveitProxyServer(const rclcpp::NodeOptions & node_options = rclcpp::NodeOptions().automatically_declare_parameters_from_overrides(true));
	// explicit __attribute__ ((visibility("default"))) MoveitProxyServer(const rclcpp::NodeOptions & node_options = rclcpp::NodeOptions());
	virtual ~MoveitProxyServer();
	
private:
	// rclcpp::Node::SharedPtr node_shered_ptr;

	rclcpp::Service<SendPlan>::SharedPtr plan_server_ptr;
	rclcpp::Service<ExecPlan>::SharedPtr exec_server_ptr;
	rclcpp::TimerBase::SharedPtr init_timer;

	void set_start(const std::shared_ptr<rmw_request_id_t> request_header, const std::shared_ptr<SendPlan::Request> request, std::shared_ptr<SendPlan::Response> response);
	void do_plan(const std::shared_ptr<rmw_request_id_t> request_header, const std::shared_ptr<SendPlan::Request> request, std::shared_ptr<SendPlan::Response> response);
	void do_exec(const std::shared_ptr<rmw_request_id_t> request_header, const std::shared_ptr<ExecPlan::Request> request, std::shared_ptr<ExecPlan::Response> response);
	void do_timer_callback();

	// moveit_interface 멤버 객체 선언
	moveit::planning_interface::MoveGroupInterface* move_group_interface_instance;

	// 플랜용 맴버 변수 선언
    moveit::planning_interface::MoveGroupInterface::Plan plan_instance;
	moveit_msgs::msg::RobotTrajectory trajectory;
	bool plan_success;

	//int private_memver_var = 6764;
	//테스트용 변수

	// void do_plan(const std::shared_ptr<moveit_proxy_interface::srv::SendPlan::Request> request, std::shared_ptr<moveit_proxy_interface::srv::SendPlan::Response> response);
	// void do_exec(const std::shared_ptr<moveit_proxy_interface::srv::ExecPlan::Request> request, std::shared_ptr<moveit_proxy_interface::srv::ExecPlan::Response> response);
};

#endif 