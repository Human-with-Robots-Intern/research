import cv2
import numpy as np
import d435cam
import time

if __name__ == "__main__":
    # 카메라 생성 및 카메라, 렌즈 파라메터 정의
    cam = d435cam.realsense_camera(720,1280,30)
    intrinsics = cam.get_intrinsics()
    cmtx = [[intrinsics.fx,0.0,intrinsics.ppx],
            [0.0,intrinsics.fy,intrinsics.ppy],
            [0.0,0.0,1.0],]
    dist = intrinsics.coeffs
    
    # aruco detector 생성
    board_type = cv2.aruco.DICT_6X6_250
    arucoDict  = cv2.aruco.getPredefinedDictionary(board_type)
    parameters = cv2.aruco.DetectorParameters_create()
    detector   = cv2.aruco.ArucoDetector(arucoDict, parameters)
    
    #realsense 카메라 초기 노출시간 확보
    time.sleep(2)
    
    #realsense 카메라로부터 촬영 이미지 가져오기
    ret,img = cam.read()
    
    #파란색상 정의
    blue_BGR = (255, 0, 0)
    
    if(ret):
        # 마커(marker) 검출
        corners, ids, rejectedCandidates = detector.detectMarkers(img)

        # 검출된 마커들의 꼭지점을 이미지에 그려 확인
        for corner in corners:
            corner = np.array(corner).reshape((4, 2))
            (topLeft, topRight, bottomRight, bottomLeft) = corner

            topRightPoint    = (int(topRight[0]),      int(topRight[1]))
            topLeftPoint     = (int(topLeft[0]),       int(topLeft[1]))
            bottomRightPoint = (int(bottomRight[0]),   int(bottomRight[1]))
            bottomLeftPoint  = (int(bottomLeft[0]),    int(bottomLeft[1]))

            cv2.circle(img, topLeftPoint, 4, blue_BGR, -1)
            cv2.circle(img, topRightPoint, 4, blue_BGR, -1)
            cv2.circle(img, bottomRightPoint, 4, blue_BGR, -1)
            cv2.circle(img, bottomLeftPoint, 4, blue_BGR, -1)
        
        cv2.imshow("img",img)
        cv2.waitKey(0)
    
    cam.release()
    cv2.destroyAllWindows()