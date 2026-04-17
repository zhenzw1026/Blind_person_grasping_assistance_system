import cv2
import time

def test_camera():
    print("Testing cameras from index 0 to 4...")
    found_any = False
    for i in range(5):
        cap = cv2.VideoCapture(i, cv2.CAP_DSHOW) # Use DirectShow on Windows for better compatibility
        if cap.isOpened():
            found_any = True
            print(f">>> Camera at index {i} successfully opened!")
            ret, frame = cap.read()
            if ret:
                print(f"    Can read frame from index {i}. Shape: {frame.shape}")
                cv2.imshow(f"Test Camera {i}", frame)
                cv2.waitKey(1000)
                cv2.destroyAllWindows()
            else:
                print(f"    Opened but could not read frame from index {i}")
            cap.release()
        else:
            print(f"    Index {i} could not be opened.")
    
    if not found_any:
        print("!!! NO CAMERAS FOUND !!! Check laptop permissions or physical connection.")

if __name__ == "__main__":
    test_camera()
