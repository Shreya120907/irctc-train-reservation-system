import sys
import time
import subprocess
import numpy as np
import cv2
import pyautogui
from PIL import ImageGrab

def record():
    print("[1/5] Initializing screen recorder...", flush=True)
    screen_size = pyautogui.size()
    fps = 15.0
    out_filename = "irctc_project_demo.mp4"
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(out_filename, fourcc, fps, (screen_size.width, screen_size.height))

    print(f"      Display Resolution: {screen_size.width}x{screen_size.height}", flush=True)

    print("[2/5] Launching IRCTC Client...", flush=True)
    client_proc = subprocess.Popen([sys.executable, "main.py"])
    time.sleep(4.0)  # Wait for PySide6 UI to load

    def capture_seconds(duration):
        frames = int(duration * fps)
        for _ in range(frames):
            img = ImageGrab.grab(bbox=(0, 0, screen_size.width, screen_size.height))
            frame = np.array(img)
            frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            out.write(frame)
            time.sleep(1.0 / fps)

    try:
        center_x = screen_size.width // 2
        center_y = screen_size.height // 2

        print("[3/5] Recording: Demonstrating UDP Mismatch Notification...", flush=True)
        capture_seconds(2.0)

        # Highlight UDP Listener box, change to 8072
        pyautogui.click(center_x + 60, center_y - 85)
        pyautogui.hotkey('ctrl', 'a')
        pyautogui.press('backspace')
        pyautogui.typewrite('8072', interval=0.08)
        capture_seconds(1.0)

        # Click 'Ping Gateway' to trigger the teacher's popup requirement
        pyautogui.click(center_x - 70, center_y - 50)
        capture_seconds(2.5)  # Captures the "UDP Service Unavailable" popup on screen

        # Dismiss dialog
        pyautogui.press('enter')
        capture_seconds(1.0)

        # Reset UDP port to 9999
        pyautogui.click(center_x + 60, center_y - 85)
        pyautogui.hotkey('ctrl', 'a')
        pyautogui.press('backspace')
        pyautogui.typewrite('9999', interval=0.08)
        pyautogui.click(center_x - 70, center_y - 50)
        capture_seconds(1.5)

        print("[4/5] Recording: Passenger Login & Live Dashboard Feed...", flush=True)
        # Type passenger username
        pyautogui.click(center_x, center_y + 15)
        pyautogui.hotkey('ctrl', 'a')
        pyautogui.typewrite('passenger01', interval=0.08)

        # Type password
        pyautogui.click(center_x, center_y + 80)
        pyautogui.hotkey('ctrl', 'a')
        pyautogui.typewrite('pass123', interval=0.08)
        capture_seconds(0.5)

        # Click Sign In
        pyautogui.click(center_x, center_y + 175)
        capture_seconds(3.0)

        # Click Broadcast Alert button in Dashboard
        pyautogui.click(center_x + 310, center_y - 250)
        capture_seconds(2.5)

        # AI Assistant Query
        pyautogui.click(center_x - 180, center_y + 60)
        pyautogui.typewrite("Will waitlist clear?", interval=0.06)
        pyautogui.press('enter')
        capture_seconds(3.0)

        # Bookings tab
        pyautogui.click(center_x - 10, center_y - 325)
        capture_seconds(2.5)

        print("[5/5] Finalizing video file...", flush=True)

    except Exception as e:
        print(f"[!] Recording error: {e}", flush=True)
    finally:
        out.release()
        client_proc.terminate()
        print(f"\n>>> Video successfully created: {out_filename}", flush=True)

if __name__ == "__main__":
    record()