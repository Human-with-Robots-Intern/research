import cv2
import numpy as np
import pyrealsense2 as rs
import time
import copy
import transforms3d

class realsense_camera:
    is_opened = False
    config = None
    intr = None

    def __init__(self, height = 480, width= 640, fps =30, use_color=True, use_depth = True):
        self.height = height
        self.width = width
        self.fps = fps
        self.use_depth = use_depth
        self.use_color = use_color

        # depth and color 설정 변수 생성
        pipeline = rs.pipeline()
        config = rs.config()

        # 디바이스 변수 얻기
        pipeline_wrapper = rs.pipeline_wrapper(pipeline)
        self.config = config
        self.pipeline = pipeline
        self.pipeline_wrapper = pipeline_wrapper

        # 디바이스 연결 체크
        if(self.can_connect()):        
            pipeline_profile = config.resolve(pipeline_wrapper)
            device = pipeline_profile.get_device()

            # 디바이스 내 color 또는 depth 모듈 체크
            found_rgb = False
            found_depth = False
            for s in device.sensors:
                if s.get_info(rs.camera_info.name) == 'Stereo Module':
                    found_depth = True
                elif s.get_info(rs.camera_info.name) == 'RGB Camera':
                    found_rgb = True

            # color 또는 depth 모듈이 없다면 비활성화
            if not found_rgb:
                use_color = False 
            if not found_depth:
                use_depth = False    

            # 모듈이 있다면 
            if(self.use_depth):
                config.enable_stream(rs.stream.depth, width, height, rs.format.z16, fps)
            if(self.use_color):
                config.enable_stream(rs.stream.color, width, height, rs.format.bgr8, fps)
            
            if(self.can_connect() and (self.use_depth or self.use_color)):
                self.is_opened = True
                pipeline.start(config)
                if(self.use_color):
                    self.intr = pipeline.get_active_profile().get_stream(rs.stream.color).as_video_stream_profile().get_intrinsics()

    def get_intrinsics(self):
        return self.intr

    def set(self,num,value):                      
        if(num == cv2.CAP_PROP_FRAME_HEIGHT):
            self.height= value
        elif(num == cv2.CAP_PROP_FRAME_WIDTH):
            self.width= value
        elif(num == cv2.CAP_PROP_FPS):
            self.fps= value
        if(self.is_opened):
            if(self.use_depth):
                self.config.enable_stream(rs.stream.depth, self.width, self.height, rs.format.z16, self.fps)
            self.config.enable_stream(rs.stream.color, self.width, self.height, rs.format.bgr8, self.fps)
            if(self.can_connect()):
                self.pipeline.stop()
                self.pipeline.start(self.config)
                self.intr = self.pipeline.get_active_profile().get_stream(rs.stream.color).as_video_stream_profile().get_intrinsics()
    
    def get(self,num):                      
        if(num == cv2.CAP_PROP_FRAME_HEIGHT):
            return self.height
        elif(num == cv2.CAP_PROP_FRAME_WIDTH):
            return  self.width
        elif(num == cv2.CAP_PROP_FPS):
            return  self.fps
    
    def can_connect(self):
        # config의 유효성 및 카메라의 연결여부 체크용도
        return self.config.can_resolve(self.pipeline_wrapper)
    
    def isOpened(self):
        return self.is_opened
    
    def release(self):
        if(not self.pipeline is None):
            if(self.isOpened()):
                if(self.can_connect()):
                    self.pipeline.stop()
    
    def read_color_depth(self):
        try:
            #파이프 라인으로부터 프레임 얻기 (100ms안에)
            frames = self.pipeline.wait_for_frames(100)
            color_frame, depth_frame = None, None
            color_image, depth_image = None, None

            #프레임에서 color와 depth 얻기
            if(self.use_color):
                color_frame = frames.get_color_frame()
            if(self.use_depth):
                depth_frame = frames.get_depth_frame()
                if(not depth_frame):
                    return False,[None, None]
            
            #numpy형으로 변환
            if(not color_frame is None):
                color_image = np.asanyarray(color_frame.get_data())
            if(not depth_frame is None):
                depth_image = np.asanyarray(depth_frame.get_data())
            
            #데이터 반환
            return True if((not color_image is None) or (not depth_image is None)) else False,[color_image, depth_image]
    
        except:
            return False,[None, None]
        
    def read(self):
        try:
            #파이프 라인으로부터 프레임 얻기 (100ms안에)
            frames = self.pipeline.wait_for_frames(100)
            if(self.use_color):
                #프레임에서 color만 얻기
                color_frame = frames.get_color_frame()
                if (not color_frame):
                    return False, None
                #numpy형으로 변환
                color_image = np.asanyarray(color_frame.get_data())
            else:
                color_image = np.zeros((self.height,self.width,3),dtype=np.uint8)
            #데이터 반환
            return True, color_image
        except:
            return False,None

class DetectArUco:
    class Marker:# 마커 데이터에 관한 내부 클래스
        def __init__(self):
            self.corner = None
            self.id = None
            self.tvec = None
            self.rvec = None
            self.quat = None

    def __init__(self, cam_arg):
        # 맴버 변수 선언
        self.marker_size = None
        self.marker_3d_edges = None

	    # 카메라, 파라미터 등의 정보를 클래스 생성자를 통해 초기화
        self.cam = cam_arg
        # aruco detector 생성
        self.marker_type = cv2.aruco.DICT_6X6_250
        self.set_marker_type(6)
        
        #realsense 카메라 초기 노출시간 확보
        time.sleep(2)

        #파란색상 정의
        self.blue_BGR = (255, 0, 0)    
        #마커 정의
        self.set_marker_size(34)
        
        # <카메라 켈리브레이션 파라미터>
        self.cmtx = None
        self.dist = None
        # <관측 결과>
        # 각 관측 결과는 현재 촬영된 정보만 활용한다.
        self.img = None
        self.num_of_ids = 0
        self.corner_list = [] # 빈 리스트로 생성
        self.id_list = [] # 빈 리스트로 생성
        self.tvec_list = [] # 빈 리스트로 생성
        self.rvec_list = [] # 빈 리스트로 생성
        self.marker_list = [] # 빈 리스트로 생성

    def __del__(self):
        # 카메라, 화면 등 할당받은 자원을 해제함.
        self.cam.release()
        cv2.destroyAllWindows()
        ...

    def set_marker_type(self, marker_type_arg):
        if(marker_type_arg == 4):
            self.marker_type = cv2.aruco.DICT_4X4_250
        elif(marker_type_arg == 5):
            self.marker_type = cv2.aruco.DICT_5X5_250
        elif(marker_type_arg == 6):
            self.marker_type = cv2.aruco.DICT_6X6_250
        elif(marker_type_arg == 7):
            self.marker_type = cv2.aruco.DICT_7X7_250
        else:
            return
        self.do_update_markerdetector()

    def do_update_markerdetector(self):
        arucoDict  = cv2.aruco.getPredefinedDictionary(self.marker_type)
        parameters = cv2.aruco.DetectorParameters()
        self.detector = cv2.aruco.ArucoDetector(arucoDict, parameters)

    def set_marker_size(self, marker_size_arg):
        self.marker_size = marker_size_arg
        self.marker_3d_edges = np.array([    
                            [-0.5*self.marker_size,0.5*self.marker_size,0],
                            [0.5*self.marker_size,0.5*self.marker_size,0],
                            [0.5*self.marker_size,-0.5*self.marker_size,0],
                            [-0.5*self.marker_size,-0.5*self.marker_size,0]], dtype = 'float32').reshape((4,1,3))

    def set_calibration_parameter(self, cmtx_arg, dist_arg):
        # 카메라 캘리브레이션 파라미터 지정 함수
        self.cmtx = cmtx_arg
        self.dist = dist_arg

    def do_init_data(self):
        self.num_of_ids = 0
        self.corner_list = [] # 빈 리스트로 초기화
        self.id_list = [] # 빈 리스트로 초기화
        self.tvec_list = [] # 빈 리스트로 초기화
        self.rvec_list = [] # 빈 리스트로 초기화
        self.marker_list = [] # 빈 리스트로 초기화

    def do_detect_marker(self):
        # 사진을 촬영하고 사진내에 존재하는 마커들의 정보를 파악하는 역할
        #realsense 카메라로부터 촬영 이미지 가져오기
        ret, img = self.cam.read()
        self.img = img
        if(ret):
            # 마커(marker) 검출
            corners, ids, rejectedCandidates = self.detector.detectMarkers(img)
            # 검출된 마커들의 꼭지점을 이미지에 그려 확인
            iter = 0
            if (ids is not None):
                for _ in ids:
                    id = ids[iter]
                    corner = corners[iter]
                    corner = np.array(corner).reshape((4, 2))
                    # corner 정보에는 각 꼭지점의 좌표정보가 담겨 있다.

                    # PnP
                    ret, rvec, tvec = cv2.solvePnP(self.marker_3d_edges, corner, np.array(self.cmtx), np.array(self.dist))
                    # 마커 디텍션이 성공한다고 PnP 계산이 성공하는 것이 아니다.
                    # 리턴 되는 변수의 타입 알아보기
                    # 아마 translation vector 와 rotation vector 로 생각된다.
                    # 여기서 계산된 정보를 담아두고 저장해 두어야 한다.
                    # print(type(rvec))# Matlike 의 타입이 파이썬에서는 <class 'numpy.ndarray'> 로 취급됨.
                    tvec_meter = tvec*1e-3 # 단위를 mm에서 m 단위로 전환
                    if(ret):
                        print(id)
                        self.id_list.append(id)
                        self.corner_list.append(corner)
                        self.tvec_list.append(tvec_meter)
                        self.rvec_list.append(rvec)
                        
                        marker = DetectArUco.Marker()
                        marker.id = id
                        marker.corner = copy.deepcopy(corner)
                        marker.tvec = copy.deepcopy(tvec_meter)
                        marker.rvec = copy.deepcopy(rvec)
                        rot_matrix = cv2.Rodrigues(np.array(rvec))[0]
                        print(rot_matrix)
                        print(rot_matrix.shape)
                        quat = transforms3d.quaternions.mat2quat(rot_matrix)
                        marker.quat = copy.deepcopy(quat)
                        self.marker_list.append(marker)                      

                    # 값을 쿼터니온 형태로 변환할 필요가 있을 듯하다.

                    iter = iter + 1# 반복에 따른 인덱스 증가
            self.num_of_ids = iter
        ...

    def draw_detected_point(self):
        img = self.img
        index = 0
        for id in self.id_list:
            id = self.id_list[index]
            corner = self.corner_list[index]
            tvec = self.tvec_list[index]
            rvec = self.rvec_list[index]

            corner = np.array(corner).reshape((4, 2))
            # corner 정보에는 각 꼭지점의 좌표정보가 담겨 있다.
            (topLeft, topRight, bottomRight, bottomLeft) = corner# 4*2 인 데이터를 1*2 4개로 분해함

            # 그림을 그리기 위한 처리과정
            topRightPoint    = (int(topRight[0]),      int(topRight[1]))
            topLeftPoint     = (int(topLeft[0]),       int(topLeft[1]))
            bottomRightPoint = (int(bottomRight[0]),   int(bottomRight[1]))
            bottomLeftPoint  = (int(bottomLeft[0]),    int(bottomLeft[1]))

            cv2.circle(img, topLeftPoint, 4, self.blue_BGR, -1)
            cv2.circle(img, topRightPoint, 4, self.blue_BGR, -1)
            cv2.circle(img, bottomRightPoint, 4, self.blue_BGR, -1)
            cv2.circle(img, bottomLeftPoint, 4, self.blue_BGR, -1)

            x=round(tvec[0][0],3)
            y=round(tvec[1][0],3)
            z=round(tvec[2][0],3)
            
            mat_rot = cv2.Rodrigues(rvec)[0]
            # rx, ry, rz = euler_from_matrix(mat_rot)
            rx, ry, rz = transforms3d.euler.quat2euler(self.marker_list[index].quat)

            rx=round(np.rad2deg(rx),3)
            ry=round(np.rad2deg(ry),3)
            rz=round(np.rad2deg(rz),3)
            text1 = "{:>3.3f},{:>3.3f},{:>3.3f}".format(x, y, z)
            text2 = "{:>3.3f},{:>3.3f},{:>3.3f}".format(rx, ry, rz)
            cv2.putText(img, text1, (int(topLeft[0]-10),   int(topLeft[1]+10)), cv2.FONT_HERSHEY_PLAIN, 1.0, (0, 0, 255))
            cv2.putText(img, text2, (int(topLeft[0]-10),   int(topLeft[1]+40)), cv2.FONT_HERSHEY_PLAIN, 1.0, (0, 0, 255))

            index = index + 1
        return img

    def show_markers(self):
        while cv2.waitKey(33) < 0:
            self.do_init_data()
            self.do_detect_marker()
            img = self.draw_detected_point()
            cv2.imshow("img", img)
        ...

    def get_marker_list(self):
        # 사진 속에서 포착된 모든 마커의 정보를 리스트 형태로 반환한다.

        # 해당 함수는 수집한 정보를 전달하는 함수로
        # 한번에 많은 메모리상의 복사가 유발된다. 
        # 정보를 외부로 전달하기위하여 필수적이지만, 
        # 병목현상이 유발될 수 있으므로 사용 상에 유의할 것
        
        return self.num_of_ids, self.marker_list


if __name__ == "__main__":
    # 카메라 생성 및 카메라, 렌즈 파라메터 정의
    cam = realsense_camera(height=1080, width=1920, fps=30, use_color=True, use_depth=False)
    # cam = realsense_camera(height=720, width=1280, fps=30, use_color=True, use_depth=False)
    # intrinsics = cam.get_intrinsics()

    detector = DetectArUco(cam)
    
    print("==============================")
    fx = 1337.647906
    fy = 1337.647906
    cx = 960.000000
    cy = 540.000000
    print("fx : {}, fy :{}".format(fx, fy))
    print("ppx : {}, ppy :{}".format(cx, cy))

    cmtx = [[fx,0.0,cx],
            [0.0,fy,cy],
            [0.0,0.0,1.0],]
    
    k1 = 0.099619
    k2 = -0.240592
    p1 = 0.004100
    p2 = -0.001100
    dist = [k1, k2, p1, p2]

    detector.set_calibration_parameter(cmtx, dist)

    detector.do_init_data()
    detector.do_detect_marker()
    img = detector.draw_detected_point()
    print(detector.get_marker_list())

    detector.show_markers()

            
