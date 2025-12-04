# import pyrealsense2 as rs
# import numpy as np
# import cv2


# def main():
#     # 1) 파이프라인 및 설정
#     pipeline = rs.pipeline()
#     config   = rs.config()
#     # 원하는 해상도·프레임레이트로 스트림 활성화
#     config.enable_stream(rs.stream.depth,  640, 480, rs.format.z16,  30)
#     config.enable_stream(rs.stream.color,  640, 480, rs.format.bgr8, 30)

#     # 2) 시작 및 align 객체 생성 (depth → color)
#     pipeline.start(config)
#     align = rs.align(rs.stream.color)

#     try:
#         while True:
#             # 3) 프레임 가져오기
#             frames = pipeline.wait_for_frames()
#             # 컬러 기준으로 depth 프레임 정렬
#             aligned_frames = align.process(frames)

#             depth_frame = aligned_frames.get_depth_frame()
#             color_frame = aligned_frames.get_color_frame()
#             if not depth_frame or not color_frame:
#                 continue

#             # 4) NumPy 배열로 변환
#             depth_image = np.asanyarray(depth_frame.get_data())
#             color_image = np.asanyarray(color_frame.get_data())

#             # 5) 화면에 동시에 표시
#             depth_colormap = cv2.applyColorMap(
#                 cv2.convertScaleAbs(depth_image, alpha=0.03),
#                 cv2.COLORMAP_JET
#             )
#             combined = np.hstack((color_image, depth_colormap))
#             cv2.imshow('Color | Depth', combined)

#             # 키 눌러 종료
#             if cv2.waitKey(1) & 0xFF == ord('q'):
#                 break

#     finally:
#         # 리소스 해제
#         pipeline.stop()
#         cv2.destroyAllWindows()

# if __name__ == '__main__':
#     main()


#!/usr/bin/env python3
import os
# Qt backend가 Wayland 대신 X11(xcb)을 쓰도록 설정
os.environ['QT_QPA_PLATFORM'] = 'xcb'

import pyrealsense2 as rs
import numpy as np
import cv2
import time

def estimate_marker_pose(corners, cam_mtx, dist, marker_size):
    """
    각 마커 코너 4점(corners[i])에 대해 solvePnP 호출.
    corners[i] shape = (1,4,2) → reshape → (4,2)
    """
    # 3D object points: 마커 중심이 (0,0,0), 한 변이 marker_size
    s = marker_size / 2.0
    obj_pts = np.array([
        [-s,  s, 0],
        [ s,  s, 0],
        [ s, -s, 0],
        [-s, -s, 0],
    ], dtype=np.float32)

    img_pts = corners.reshape(-1, 2).astype(np.float32)
    # solvePnP 반환: rvec, tvec
    success, rvec, tvec = cv2.solvePnP(obj_pts, img_pts, cam_mtx, dist, flags=cv2.SOLVEPNP_IPPE_SQUARE)
    if not success:
        return None, None
    return rvec, tvec

def detect_and_draw_aruco(frame, cam_mtx, dist, detector, marker_size):
    undist = cv2.undistort(frame, cam_mtx, dist)
    corners, ids, _ = detector.detectMarkers(undist)
    if ids is not None:
        cv2.aruco.drawDetectedMarkers(undist, corners, ids)
        for i, marker_id in enumerate(ids.flatten()):
            rvec, tvec = estimate_marker_pose(corners[i], cam_mtx, dist, marker_size)
            if rvec is None:
                continue
            # 좌표축 그리기
            cv2.drawFrameAxes(
                undist, cam_mtx, dist,
                rvec, tvec,
                marker_size/2, 2
            )
            # 텍스트 표시
            t = tvec.flatten()
            text = f"ID:{marker_id}  ({t[0]:.2f},{t[1]:.2f},{t[2]:.2f})m"
            # 코너 중심
            c = corners[i][0]
            cx, cy = int(c[:,0].mean()), int(c[:,1].mean())
            cv2.putText(undist, text, (cx-60, cy-30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,0,255), 2)
    return undist

def main():
    WIDTH, HEIGHT = 640, 480
    # RealSense 스트리밍 설정
    pipeline = rs.pipeline()
    config   = rs.config()
    config.enable_stream(rs.stream.depth, WIDTH, HEIGHT, rs.format.z16, 30)
    config.enable_stream(rs.stream.color, WIDTH, HEIGHT, rs.format.bgr8, 30)
    pipeline.start(config)
    align = rs.align(rs.stream.color)

    # 캘리브레이션 없을 때의 대략 파라미터
    f = WIDTH
    cam_mtx = np.array([[f, 0, WIDTH/2],
                        [0, f, HEIGHT/2],
                        [0, 0,     1   ]], np.float32)
    dist = np.zeros((5,1), np.float32)

    # ArUco 초기화
    aruco_dict  = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_250)
    params      = cv2.aruco.DetectorParameters_create()
    detector    = cv2.aruco.ArucoDetector(aruco_dict, params)
    marker_size = 0.05  # [m]

    print("Starting RealSense + ArUco (no calib & solvePnP)...")
    time.sleep(1)

    try:
        while True:
            frames = pipeline.wait_for_frames()
            aligned = align.process(frames)
            d = aligned.get_depth_frame()
            c = aligned.get_color_frame()
            if not d or not c:
                continue

            color_img = np.asanyarray(c.get_data())
            depth_img = np.asanyarray(d.get_data())

            out = detect_and_draw_aruco(color_img, cam_mtx, dist, detector, marker_size)

            depth_colormap = cv2.applyColorMap(
                cv2.convertScaleAbs(depth_img, alpha=0.03),
                cv2.COLORMAP_JET
            )
            combined = np.hstack((out, depth_colormap))

            cv2.imshow('RealSense ArUco (no calib)', combined)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    finally:
        pipeline.stop()
        cv2.destroyAllWindows()

if __name__ == '__main__':
    main()








from robot_manager_interface.srv import RobotManager
import sys
import rclpy
from rclpy.node import Node


class RobotManagerClient(Node):

    def __init__(self):
        super().__init__('robot_manager_client') # change 'robot_manager_client' to our node name -> have to match with server
        self.cli_h = self.create_client(RobotManager, '/robot_command') # change name '/robot_command' -> have to match with server
        while not self.cli_h.wait_for_service(timeout_sec=1.0):
            self.get_logger().info('service not available, waiting again...')
        self.client_entity_list = [self.cli_h]

    def send_request(self, robot_model, instruction, A, B):
        req_temp = RobotManager.Request()      
        req_temp.robot_model = robot_model
        req_temp.instruction = instruction
        req_temp.a = A                          
        req_temp.b = B
        future = self.client_entity_list[robot_model].call_async(req_temp)
        return future

def main(args=None):
    rclpy.init(args=args)
    robot_manager_service_client = RobotManagerClient()
    # put data 'robot_model, instruction, A, B. (int)
    # robot_model is always 0. 
    future = robot_manager_service_client.send_request(robot_model, instruction, A, B)
    while rclpy.ok():
        rclpy.spin_once(robot_manager_service_client)
        if future.done():
            try:
                response = future.result()
            except Exception as e:
                robot_manager_service_client.get_logger().info(
                    'Service call failed %r' % (e,))
                sys.exit('종료')
            else:
                if response.success == True:
                    robot_manager_service_client.get_logger().info(
                        'Result = successed')  
                else:
                    robot_manager_service_client.get_logger().info(
                        'Result = failed')  
                    sys.exit('종료')
            break
    robot_manager_service_client.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()