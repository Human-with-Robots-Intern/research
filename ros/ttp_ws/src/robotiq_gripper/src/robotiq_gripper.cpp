#include "robotiq_gripper.hpp"

uint8_t truncate(double input_val, uint8_t bottom, uint8_t top)
{
	uint8_t return_val = (uint8_t)input_val;
	if(return_val > top)
	{
		return_val = top;
	}
	if(return_val < bottom)
	{
		return_val = bottom;
	}
	return return_val;
}

RobotiqGripper::RobotiqGripper(const rclcpp::NodeOptions & node_options /*= rclcpp::NodeOptions()*/)
: Node("robotiq_gripper", node_options)
{
	stringstream ss;

	ss << "RobotiqGripper Constructor start" << endl; 
	RCLCPP_INFO(this->get_logger(), ss.str().c_str());
	ss.str(std::string());//flush stringstream

	//ros2 parameter 설정
	string port_name = (*this).declare_parameter("port_name", "/dev/ttyUSB0");
	int baudrate = (*this).declare_parameter("baudrate", 115200);
	int rate = (*this).declare_parameter("rate", 20);

	port_name = (*this).get_parameter("port_name").as_string();
	baudrate = (*this).get_parameter("baudrate").as_int();
	rate = (*this).get_parameter("rate").as_int();

	ss << "port_name : " << port_name << ", baudrate : " << baudrate << ", rate : " << rate << endl; 
	RCLCPP_INFO(this->get_logger(), ss.str().c_str());
	ss.str(std::string());//flush stringstream



	//serial communication object 생성
	modbus_instance = modbus_new_rtu(port_name.c_str(), baudrate, 'N', 8, 1);
	assert(modbus_instance != NULL);
	modbus_set_slave(modbus_instance, 9);
	if(modbus_connect(modbus_instance) == -1)
	{
		modbus_free(modbus_instance);
		assert(false);
	}

	//시스템 초기화하는 레지스터의 값 전달로 추정
	uint16_t send_registers[3] = {0, 0, 0};
	modbus_write_registers(modbus_instance, 0x3E8, 3, send_registers);
	// rclcpp::Duration sleep_duration = rclcpp::Duration::from_seconds(0.5);
	// double seconds = sleep_duration.seconds();
	rclcpp::sleep_for(500ms);

	// 콜백 중에서 modbus_instance 를 통해 통신을 활용하는 콜백이 존재하므로 
	// 통신이 초기화 된 이후에 통신하기 위해서 rclcpp::sleep_for(500ms) 명령 이후에 콜백 등록

	//ros2 콜백 설정
	control_comunication_timer_ptr = (*this).create_wall_timer(1000ms/rate, std::bind(&RobotiqGripper::callback_control_comunication_timer, this));
	
	// 함수의 바인딩 
	auto callback_set_gripper_state_bind = std::bind(&RobotiqGripper::callback_set_gripper_state, this, std::placeholders::_1, std::placeholders::_2, std::placeholders::_3);
	auto callback_get_gripper_state_bind = std::bind(&RobotiqGripper::callback_get_gripper_state, this, std::placeholders::_1, std::placeholders::_2, std::placeholders::_3);

	set_gripper_server_ptr = (*this).create_service<robotiq_gripper_interface::srv::SetGripperStateCommand>(
		"set_gripper_state",
		callback_set_gripper_state_bind
	);
	get_gripper_server_ptr = (*this).create_service<robotiq_gripper_interface::srv::GetGripperStateCommand>(
		"get_gripper_state",
		callback_get_gripper_state_bind
	);
	
	gripper_state_publisher_ptr = (*this).create_publisher<robotiq_gripper_interface::msg::GripperState>(
		"gripper_state",
		10//qos_history_depth
	);
	
	gripper_joint_state_publisher_ptr = (*this).create_publisher<sensor_msgs::msg::JointState>(
		"gripper_joint_state",
		10//qos_history_depth
	);

	ss << "RobotiqGripper Constructor finished" << endl; 
	RCLCPP_INFO(this->get_logger(), ss.str().c_str());
	ss.str(std::string());//flush stringstream
}

RobotiqGripper::~RobotiqGripper()
{
	
}

void RobotiqGripper::callback_set_gripper_state([[maybe_unused]] const std::shared_ptr<rmw_request_id_t> request_header, const std::shared_ptr<SetGripper::Request> request, std::shared_ptr<SetGripper::Response> response)
{
	// 0을 여는것으로 설정
	// 0.85를 닫는 것으로 설정
	// 1로 닫히면 힘이 너무 세다고 한다.

	stringstream ss;

	bool position_condition = ((*request).position <= 1.0 && (*request).position >= 0.0);
	bool speed_condition = ((*request).speed <= 1.0 && (*request).speed >= 0.0);
	bool force_condition = ((*request).force <= 1.0 && (*request).force >= 0.0);
	if(position_condition == false)
	{
		ss << "Gripper position is in [0...1]..."; 
		RCLCPP_INFO(this->get_logger(), ss.str().c_str());
		ss.str(std::string());//flush stringstream
	}

	if(speed_condition == false)
	{
		ss << "Gripper speed is in [0...1]..."; 
		RCLCPP_INFO(this->get_logger(), ss.str().c_str());
		ss.str(std::string());//flush stringstream
	}

	if(force_condition == false)
	{
		ss << "Gripper force is in [0...1]..."; 
		RCLCPP_INFO(this->get_logger(), ss.str().c_str());
		ss.str(std::string());//flush stringstream
	}

	if(position_condition && speed_condition && force_condition)
	{
		// 정상적인 요청을 받았을 경우에는 상태 값을 업데이트
		gripper_pos = (*request).position;
		gripper_speed = (*request).speed;
		gripper_force = (*request).force;

		gripper_pos_scaled = truncate(gripper_pos*255.0, 0, 255);
		gripper_speed_scaled = truncate(gripper_speed*255.0, 0, 255);
		gripper_force_scaled = truncate(gripper_force*255.0, 0, 255);
		
		(*response).result = true;
	}
	else
	{
		// 비정상적인 요청을 받았을 경우에는 상태 값을 업데이트하지 않고 무시
		(*response).result = false;
	}
}

void RobotiqGripper::callback_get_gripper_state([[maybe_unused]] const std::shared_ptr<rmw_request_id_t> request_header, [[maybe_unused]] const std::shared_ptr<GetGripper::Request> request, std::shared_ptr<GetGripper::Response> response)
{
	(*response).position = gripper_pos;
	(*response).speed = gripper_speed;
	(*response).force = gripper_force;
}

void RobotiqGripper::callback_control_comunication_timer()
{
	/*
	출력을 통한 통신 콜백 상태 확인 
	stringstream ss;

	ss << "callback_control_comunication_timer" << endl; 
	RCLCPP_INFO(this->get_logger(), ss.str().c_str());
	*/
	uint16_t send_registers[3] = {0, 0, 0};

	send_registers[0] = 0x0900;  // gACT and gGTO is always on //레제스터의 주소는 16bit 기반 주소
	send_registers[1] = gripper_pos_scaled & 0x00FF;//레지스터의 high 8bit 부분을 모두 0으로 masking 함 혹여나 입력이 레지스터의 범위를 침범하지 않기 위함
	send_registers[2] = (gripper_speed_scaled << 8) + (gripper_force_scaled);

	modbus_write_registers(modbus_instance, 0x3E8, 3, send_registers);
	rclcpp::sleep_for(1ms);

	// Receive status from Gripper
	uint16_t recv_registers[3] = {0, };
	modbus_read_registers(modbus_instance, 0x7D0, 3, recv_registers);

	auto gripper_msg = robotiq_gripper_interface::msg::GripperState();
	gripper_msg.g_act = (uint8_t)(recv_registers[0] >> 8) & 0x01;
	gripper_msg.g_gto = (uint8_t)(recv_registers[0] >> 11) & 0x01;
	gripper_msg.g_sta = (uint8_t)(recv_registers[0] >> 12) & 0x03;
	gripper_msg.g_obj = (uint8_t)(recv_registers[0] >> 14) & 0x03;
	gripper_msg.g_flt = (uint8_t)(recv_registers[1] >> 8) & 0x0F;
	gripper_msg.g_pr = (uint8_t)(recv_registers[1]) & 0xFF;
	gripper_msg.g_po = (uint8_t)(recv_registers[2] >> 8) & 0xFF;
	gripper_msg.g_cu = (uint8_t)(recv_registers[2]) & 0xFF;

	(*gripper_state_publisher_ptr).publish(gripper_msg);

	gripper_pos = gripper_msg.g_po / 255.0;
	// gripper_speed = gripper_speed_scaled / 255.0;
	// gripper_speed = 0.0;
	gripper_force = gripper_msg.g_cu / 255.0;

	auto joint_state_msg = sensor_msgs::msg::JointState();
	joint_state_msg.header.stamp = this->get_clock()->now();
	joint_state_msg.name.push_back("finger_joint");
	joint_state_msg.position.push_back(gripper_pos);
	joint_state_msg.velocity.push_back(gripper_speed);
	joint_state_msg.effort.push_back(gripper_force);

	(*gripper_joint_state_publisher_ptr).publish(joint_state_msg);//moveit 용 joint state 값 전달 publisher 인 것으로 추정
}

RCLCPP_COMPONENTS_REGISTER_NODE(RobotiqGripper)
