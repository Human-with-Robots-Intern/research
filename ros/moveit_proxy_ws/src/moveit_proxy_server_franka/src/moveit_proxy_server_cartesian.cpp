#include "moveit_proxy_server_cartesian.hpp"

#include "rclcpp_components/register_node_macro.hpp"

using SendPlan = moveit_proxy_interface::srv::SendPlan;
using ExecPlan = moveit_proxy_interface::srv::ExecPlan;
using GetPose = moveit_proxy_interface::srv::GetPose;

//const std::shared_ptr<rmw_request_id_t> request_header 를 적용하니 에러가 발생하지 않는다...!
//https://robotics.stackexchange.com/questions/88250/ros2-error-creating-a-service-server-as-a-member-function
void MoveitProxyServer::do_plan([[maybe_unused]] const std::shared_ptr<rmw_request_id_t> request_header, const std::shared_ptr<SendPlan::Request> request, std::shared_ptr<SendPlan::Response> response)
{
	cout << "test_do_plan" << endl;
	cout << (*request).goal_pose.position.x << endl;
	cout << (*request).goal_pose.position.y << endl;
	cout << (*request).goal_pose.position.z << endl;
	cout << (*request).goal_pose.orientation.x << endl;
	cout << (*request).goal_pose.orientation.y << endl;
	cout << (*request).goal_pose.orientation.z << endl;
	cout << (*request).goal_pose.orientation.w << endl;

	geometry_msgs::msg::Pose start_pose;
	geometry_msgs::msg::Pose goal_pose;

	geometry_msgs::msg::PoseStamped current_pose_stamped = (*this).move_group_interface_instance->getCurrentPose();

	start_pose = current_pose_stamped.pose;// Start pose를 Current pose 로 한다.
	goal_pose = (*request).goal_pose;

	std::vector<geometry_msgs::msg::Pose> waypoints;
	waypoints.push_back(start_pose);  // up and left
	waypoints.push_back(goal_pose);

	cout << "start p_x : " << waypoints[0].position.x << endl;
	cout << "start p_y : " << waypoints[0].position.y << endl;
	cout << "start p_z : " << waypoints[0].position.z << endl;
	cout << "start o_x : " << waypoints[0].orientation.x << endl;
	cout << "start o_y : " << waypoints[0].orientation.y << endl;
	cout << "start o_z : " << waypoints[0].orientation.z << endl;
	cout << "start o_w : " << waypoints[0].orientation.w << endl;

	cout << "---------" << endl;

	cout << "goal p_x : " << waypoints[1].position.x << endl;
	cout << "goal p_y : " << waypoints[1].position.y << endl;
	cout << "goal p_z : " << waypoints[1].position.z << endl;
	cout << "goal o_x : " << waypoints[1].orientation.x << endl;
	cout << "goal o_y : " << waypoints[1].orientation.y << endl;
	cout << "goal o_z : " << waypoints[1].orientation.z << endl;
	cout << "goal o_w : " << waypoints[1].orientation.w << endl;
	cout << "waypoint len : " << waypoints.size() << endl;
	// 멤버 함수 테스트 cout<<private_memver_var<<endl;
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
	cout<<"test_do_plan_finished"<<endl;
}

void MoveitProxyServer::do_exec([[maybe_unused]] const std::shared_ptr<rmw_request_id_t> request_header, [[maybe_unused]] const std::shared_ptr<ExecPlan::Request> request, std::shared_ptr<ExecPlan::Response> response)
{
	//[[maybe_unused]] 변수를 사용하지 않아도 오류를 내지 않도록 하는 매크로, c++17 이상에서 지원
	cout<<"test_do_exec"<<endl;
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
	cout<<"test_do_exec_finished"<<endl;
}

void MoveitProxyServer::get_pose([[maybe_unused]] const std::shared_ptr<rmw_request_id_t> request_header, [[maybe_unused]] const std::shared_ptr<GetPose::Request> request, std::shared_ptr<GetPose::Response> response)
{
	//[[maybe_unused]] 변수를 사용하지 않아도 오류를 내지 않도록 하는 매크로, c++17 이상에서 지원
	cout<<"test_get_pose"<<endl;
	// rclcpp::sleep_for(std::chrono::seconds(3));//테스트용 시간 지연
	geometry_msgs::msg::PoseStamped current_pose_stamped = (*this).move_group_interface_instance->getCurrentPose();
	
	// 현재 위치값 출력 및 확인
	cout << current_pose_stamped.pose.position.x << endl;
	cout << current_pose_stamped.pose.position.y << endl;
	cout << current_pose_stamped.pose.position.z << endl;
	cout << current_pose_stamped.pose.orientation.x << endl;
	cout << current_pose_stamped.pose.orientation.y << endl;
	cout << current_pose_stamped.pose.orientation.z << endl;
	cout << current_pose_stamped.pose.orientation.w << endl;

	(*response).set__pose(current_pose_stamped.pose);

	cout<<"test_get_pose_finished"<<endl;
}

//---멤버 함수가 아닌 보통의 함수 포인터를 전달해야하는 문제에서의 오류였다.

void MoveitProxyServer::do_timer_callback()
{
	//set move_group_interface_instance
	cout << "init move_group_interface_instance" << endl;
	// auto node_shered_ptr = shared_from_this();
	// move_group_interface_instance = new moveit::planning_interface::MoveGroupInterface(std::make_shared<rclcpp::Node>(node_shered_ptr), "panda_arm");
	move_group_interface_instance = new moveit::planning_interface::MoveGroupInterface(shared_from_this(), "panda_arm");
	// move_group_interface_instance = new moveit::planning_interface::MoveGroupInterface(shared_from_this(), "ur_manipulator");
	geometry_msgs::msg::PoseStamped current_pose_stamped = (*this).move_group_interface_instance->getCurrentPose();
	(*init_timer).cancel();

}

MoveitProxyServer::MoveitProxyServer(const rclcpp::NodeOptions & node_options /*= rclcpp::NodeOptions()*/)
: Node("moveit_proxy_server", node_options)
// : node_shered_ptr{ std::make_shared<MoveitProxyServer>("moveit_proxy_server", node_options)}
{
// 비어있는 클래스 생성자를 선언

	// ROS2 파라미터 선언
	string node_namespace = declare_parameter("namespace", "");
	// ROS2 파라미터 값 가져오기
	node_namespace = get_parameter("namespace").as_string();
	
	//서비스를 위한 콜백 그룹 생성
	//자기 자신에 대해서만 상호 배제를 충분히 하는 방향으로 콜백 그롭 선언
	do_plan_bind_cb_group_ptr = this->create_callback_group(rclcpp::CallbackGroupType::MutuallyExclusive);
	do_exec_bind_cb_group_ptr = this->create_callback_group(rclcpp::CallbackGroupType::MutuallyExclusive);
	get_pose_bind_cb_group_ptr = this->create_callback_group(rclcpp::CallbackGroupType::MutuallyExclusive);

	//std::bind 를 통한 함수 포인터 생성
	//멤버 함수를 바인드 하는 경우 주소연산이 필요...?
	auto do_plan_bind = std::bind(&MoveitProxyServer::do_plan, this, std::placeholders::_1, std::placeholders::_2, std::placeholders::_3);
	auto do_exec_bind = std::bind(&MoveitProxyServer::do_exec, this, std::placeholders::_1, std::placeholders::_2, std::placeholders::_3);
	auto do_get_pose = std::bind(&MoveitProxyServer::get_pose, this, std::placeholders::_1, std::placeholders::_2, std::placeholders::_3);

	do_plan_server_ptr = create_service<moveit_proxy_interface::srv::SendPlan>(
		"moveit_proxy_send_plan",
		do_plan_bind,
		rmw_qos_profile_services_default,//rclcpp::Node 객체에서 상속받은 맴버 변수인 듯 하다.
		do_plan_bind_cb_group_ptr
	);

	do_exec_server_ptr = create_service<moveit_proxy_interface::srv::ExecPlan>(
		"moveit_proxy_exec_plan",
		do_exec_bind,
		rmw_qos_profile_services_default,//rclcpp::Node 객체에서 상속받은 맴버 변수인 듯 하다.
		do_exec_bind_cb_group_ptr
	);

	get_pose_server_ptr = create_service<moveit_proxy_interface::srv::GetPose>(
		"moveit_proxy_get_pose",
		do_get_pose,
		rmw_qos_profile_services_default,//rclcpp::Node 객체에서 상속받은 맴버 변수인 듯 하다.
		get_pose_bind_cb_group_ptr
	);
	// move_group_interface_instance = moveit::planning_interface::MoveGroupInterface(shared_from_this(), "panda_arm");
	// using moveit::planning_interface::MoveGroupInterface;
	// auto move_group_interface = MoveGroupInterface(shared_from_this(), "panda_arm");

	init_timer = (*this).create_wall_timer(500ms, std::bind(&MoveitProxyServer::do_timer_callback, this));

	stringstream ss;
	ss << "defualt constructor" << endl;
	ss << "node name : " <<  node_namespace + "/moveit_client_server"  << endl;

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

