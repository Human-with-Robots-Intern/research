#include "moveit_proxy_server_cartesian.hpp"

#include "rclcpp_components/register_node_macro.hpp"

using SendPlan = moveit_proxy_interface::srv::SendPlan;
using ExecPlan = moveit_proxy_interface::srv::ExecPlan;

void set_start([[maybe_unused]] const std::shared_ptr<rmw_request_id_t> request_header, const std::shared_ptr<SendPlan::Request> request, std::shared_ptr<SendPlan::Response> response)
{
	std::cout<<"test_do_plan"<<std::endl;
	std::cout<<(*request).goal_pose.position.x<<std::endl;
	std::cout<<(*request).goal_pose.position.y<<std::endl;
	std::cout<<(*request).goal_pose.position.z<<std::endl;
	
}

//const std::shared_ptr<rmw_request_id_t> request_header 를 적용하니 에러가 발생하지 않는다...!
//https://robotics.stackexchange.com/questions/88250/ros2-error-creating-a-service-server-as-a-member-function
void MoveitProxyServer::do_plan([[maybe_unused]] const std::shared_ptr<rmw_request_id_t> request_header, const std::shared_ptr<SendPlan::Request> request, std::shared_ptr<SendPlan::Response> response)
{
	std::cout<<"test_do_plan"<<std::endl;
	std::cout<<(*request).goal_pose.position.x<<std::endl;
	std::cout<<(*request).goal_pose.position.y<<std::endl;
	std::cout<<(*request).goal_pose.position.z<<std::endl;
	

	geometry_msgs::msg::Pose start_pose;
	geometry_msgs::msg::Pose goal_pose;

	start_pose = previous_pose;
	goal_pose = (*request).goal_pose;

	std::vector<geometry_msgs::msg::Pose> waypoints;
	waypoints.push_back(start_pose);  // up and left
	waypoints.push_back(goal_pose);

	cout << "start x : " << waypoints[0].position.x << endl;
	cout << "start y : " << waypoints[0].position.y << endl;
	cout << "start z : " << waypoints[0].position.z << endl;

	cout << "goal x : " << waypoints[1].position.x << endl;
	cout << "goal y : " << waypoints[1].position.y << endl;
	cout << "goal z : " << waypoints[1].position.z << endl;
	cout << "waypoint len : " << waypoints.size() << endl;
	// 멤버 함수 테스트 std::cout<<private_memver_var<<std::endl;
	// move_group_interface_instance->setStartStateToCurrentState();
	// move_group_interface_instance->setPoseTarget((*request).goal_pose);
	// move_group_interface_instance->setGoalTolerance(0.01);
    // plan_success = static_cast<bool>(move_group_interface_instance->plan(plan_instance));//msg가 & 참조 변수로 작용하여 함수 호출이후 덮어쓰기 됨에 주의
	
	const double jump_threshold = 0.0;
	const double eef_step = 0.001;
	double fraction = move_group_interface_instance->computeCartesianPath(waypoints, eef_step, jump_threshold, trajectory);
	
	if(fraction < 0.0)// Return -1.0 in case of error
	{
		plan_success = false;
	}
	else
	{
		plan_success = true;
	}

	if(plan_success == true)
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

void MoveitProxyServer::do_exec([[maybe_unused]] const std::shared_ptr<rmw_request_id_t> request_header, [[maybe_unused]] const std::shared_ptr<ExecPlan::Request> request, std::shared_ptr<ExecPlan::Response> response)
{
	//[[maybe_unused]] 변수를 사용하지 않아도 오류를 내지 않도록 하는 매크로, c++17 이상에서 지원
	std::cout<<"test_do_exec"<<std::endl;
	// rclcpp::sleep_for(std::chrono::seconds(3));//테스트용 시간 지연
	if(plan_success == true) {
    	// move_group_interface_instance->move();//현재 위치가 이미 골에 도달한지 확인한 후 execute해 주므로 보다 안전한 방법의 명령어
		move_group_interface_instance->execute(trajectory);
		(*response).result = true;//boolean
	}
	else
	{
		RCLCPP_ERROR(this->get_logger(), "Executing failed!");
		(*response).result = false;//boolean
	}
	std::cout<<"test_do_exec_finished"<<std::endl;
}

//---멤버 함수가 아닌 보통의 함수 포인터를 전달해야하는 문제에서의 오류였다.


void MoveitProxyServer::do_timer_callback()
{
	//set move_group_interface_instance
	std::cout << "init move_group_interface_instance" << std::endl;
	// auto node_shered_ptr = shared_from_this();
	// move_group_interface_instance = new moveit::planning_interface::MoveGroupInterface(std::make_shared<rclcpp::Node>(node_shered_ptr), "panda_arm");
	// move_group_interface_instance = new moveit::planning_interface::MoveGroupInterface(shared_from_this(), "panda_arm");
	move_group_interface_instance = new moveit::planning_interface::MoveGroupInterface(shared_from_this(), "ur_manipulator");
	cout << "test : " << test << endl; 
	(*init_timer).cancel();

}


MoveitProxyServer::MoveitProxyServer(const rclcpp::NodeOptions & node_options /*= rclcpp::NodeOptions()*/)
: Node("moveit_proxy_server", node_options)
// : node_shered_ptr{ std::make_shared<MoveitProxyServer>("moveit_proxy_server", node_options)}
{
// 비어있는 클래스 생성자를 선언

	std::cout<<"ur_manipulator_cartesian"<<std::endl;

	// ROS2 파라미터 선언
	string node_namespace = declare_parameter("namespace", "");
	// ROS2 파라미터 값 가져오기
	node_namespace = get_parameter("namespace").as_string();
	
	//std::bind 를 통한 함수 포인터 생성
	//멤버 함수를 바인드 하는 경우 주소연산이 필요...?
	auto do_set_start_bind = std::bind(&MoveitProxyServer::set_start, this, std::placeholders::_1, std::placeholders::_2, std::placeholders::_3);
	auto do_plan_bind = std::bind(&MoveitProxyServer::do_plan, this, std::placeholders::_1, std::placeholders::_2, std::placeholders::_3);
	auto do_exec_bind = std::bind(&MoveitProxyServer::do_exec, this, std::placeholders::_1, std::placeholders::_2, std::placeholders::_3);

	plan_server_ptr = create_service<moveit_proxy_interface::srv::SendPlan>(
		"/moveit_proxy_send_plan_start",
		do_plan_bind
	);

	plan_server_ptr = create_service<moveit_proxy_interface::srv::SendPlan>(
		"/moveit_proxy_send_plan_goal",
		do_plan_bind
	);

	exec_server_ptr = create_service<moveit_proxy_interface::srv::ExecPlan>(
		"/moveit_proxy_exec_plan",
		do_exec_bind
	);
	// move_group_interface_instance = moveit::planning_interface::MoveGroupInterface(shared_from_this(), "panda_arm");
	// using moveit::planning_interface::MoveGroupInterface;
	// auto move_group_interface = MoveGroupInterface(shared_from_this(), "panda_arm");
	

	init_timer = (*this).create_wall_timer(500ms, std::bind(&MoveitProxyServer::do_timer_callback, this));

	stringstream ss;
	ss << "defualt constructor" << std::endl;
	ss << "node name : " <<  node_namespace + "/moveit_client_server"  << std::endl;

	RCLCPP_INFO(this->get_logger(), ss.str().c_str());

}

MoveitProxyServer::~MoveitProxyServer()
{
	//rclcpp::shutdown();
	//오히려 노드가 제대로 종료되지 못하도록 하는 오류를 발생 시키는 듯 하다.
	delete move_group_interface_instance;
}

// RCLCPP_COMPONENTS_REGISTER_NODE(action_tutorials_cpp::FibonacciActionClient)
// 생각없이 복붙만 하여 클래스의 이름을 바꾸어 주는 것을 깜빡하여 고쳐줌.
RCLCPP_COMPONENTS_REGISTER_NODE(MoveitProxyServer)
// 이 매크로의 역할은 node factory의 class loader가 사용자가 만든 클래스를 가져다 활용하도록 해주는 역할.

