"""
Automated Screen Demonstration & Recording Tool for IRCTC Desktop Simulator.
Focus: Complete Administrator Walkthrough (Role selection, admin login,
fleet management, system statistics, and audit logs).
Output: irctc_admin_demo.mp4
"""

import sys
import time
import subprocess
import cv2
import numpy as np
import pyautogui
from PIL import ImageGrab

def record_admin_walkthrough():
    print("[1/5] Initializing screen recorder for Admin Walkthrough...", flush=True)
    screen_size = pyautogui.size()
    fps = 15.0
    out_filename = "irctc_admin_demo.mp4"
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(out_filename, fourcc, fps, (screen_size.width, screen_size.height))

    print(f"      Display Resolution: {screen_size.width}x{screen_size.height}", flush=True)

    print("[2/5] Launching IRCTC Client...", flush=True)
    client_proc = subprocess.Popen([sys.executable, "main.py"])
    time.sleep(4.0)

    def capture_seconds(duration: float):
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

        print("[3/5] Recording: Selecting Admin Role & Entering Credentials...", flush=True)
        capture_seconds(1.5)

        # 1. Switch Role dropdown to 'Railway Admin' / 'Administrator / Staff'
        # Click on role combo box
        pyautogui.click(center_x + 50, center_y + 130)
        time.sleep(0.3)
        pyautogui.press('down')
        pyautogui.press('enter')
        capture_seconds(1.0)

        # 2. Type Admin Username
        pyautogui.click(center_x, center_y + 15)
        pyautogui.hotkey('ctrl', 'a')
        pyautogui.press('backspace')
        pyautogui.typewrite('admin', interval=0.08)
        capture_seconds(0.5)

        # 3. Type Admin Password
        pyautogui.click(center_x, center_y + 80)
        pyautogui.hotkey('ctrl', 'a')
        pyautogui.press('backspace')
        pyautogui.typewrite('admin', interval=0.08)
        capture_seconds(0.8)

        # 4. Click 'Sign In to IRCTC'
        pyautogui.click(center_x, center_y + 175)
        capture_seconds(3.0)  # Captures loading & hydrating Admin workspace

        print("[4/5] Recording: Admin Dashboard & Console Operations...", flush=True)
        
        # Click on 'Admin Console' or fleet management tab in navigation bar
        pyautogui.click(center_x + 120, center_y - 325)
        capture_seconds(3.0)

        # Scroll / inspect train schedules and seat inventory
        pyautogui.scroll(-300)
        capture_seconds(2.0)
        pyautogui.scroll(300)
        capture_seconds(1.5)

        # Click on Train Fleet search or filter bar if present
        pyautogui.click(center_x - 100, center_y - 120)
        pyautogui.typewrite("Rajdhani", interval=0.07)
        capture_seconds(2.5)

        # Show live UDP system notification broadcast from Admin console
        pyautogui.click(center_x + 280, center_y - 250)
        capture_seconds(2.5)

        print("[5/5] Finalizing video file...", flush=True)

    except Exception as e:
        print(f"[!] Recording error: {e}", flush=True)
    finally:
        out.release()
        client_proc.terminate()
        print(f"\n>>> Admin demo video saved as: {out_filename}", flush=True)

if __name__ == "__main__":
    record_admin_walkthrough()