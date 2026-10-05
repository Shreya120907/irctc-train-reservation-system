"""
Automated Screen Demonstration & Recording Tool for IRCTC Desktop Simulator.
Captures screen actions: Login, UDP port mismatch alert, Admin console, 
Booking ticket, live UDP broadcast alert, and Cancellation.
Outputs: irctc_project_demo.mp4
"""

import time
import subprocess
import cv2
import numpy as np
import pyautogui
from PIL import ImageGrab

# Video Output Setup
SCREEN_SIZE = pyautogui.size()
FPS = 15.0
OUT_FILENAME = "irctc_project_demo.mp4"
fourcc = cv2.VideoWriter_fourcc(*"mp4v")
out = cv2.VideoWriter(OUT_FILENAME, fourcc, FPS, (SCREEN_SIZE.width, SCREEN_SIZE.height))

print(">>> Starting IRCTC Client application...")
client_proc = subprocess.Popen(["python", "main.py"])
time.sleep(3.5)

def capture_frames(duration_seconds: float):
    """Captures desktop frames to video file."""
    frames_to_record = int(duration_seconds * FPS)
    for _ in range(frames_to_record):
        img = ImageGrab.grab(bbox=(0, 0, SCREEN_SIZE.width, SCREEN_SIZE.height))
        frame = np.array(img)
        frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        out.write(frame)
        time.sleep(1.0 / FPS)

try:
    print(">>> Recording Part 1: Gateway & UDP Port Mismatch Notification...")
    # Give initial preview
    capture_frames(2.0)

    # 1. Double-click UDP spinbox, type mismatched port '8888', and Ping Gateway
    center_x = SCREEN_SIZE.width // 2
    center_y = SCREEN_SIZE.height // 2

    # Click on the UDP spinbox field
    pyautogui.click(center_x + 50, center_y - 88)
    pyautogui.hotkey('ctrl', 'a')
    pyautogui.press('backspace')
    pyautogui.typewrite('8888', interval=0.1)
    capture_frames(1.0)

    # Click 'Ping Gateway' button
    pyautogui.click(center_x - 80, center_y - 50)
    capture_frames(2.5)  # Records the popup: "UDP Service Unavailable"

    # Press Enter or Space to dismiss the warning popup
    pyautogui.press('enter')
    capture_frames(1.5)

    # Restore UDP port to 9999
    pyautogui.click(center_x + 50, center_y - 88)
    pyautogui.hotkey('ctrl', 'a')
    pyautogui.press('backspace')
    pyautogui.typewrite('9999', interval=0.1)
    pyautogui.click(center_x - 80, center_y - 50)
    capture_frames(1.5)

    print(">>> Recording Part 2: Passenger Login & Dashboard Navigation...")
    # Click Username field and type passenger credentials
    pyautogui.click(center_x, center_y + 15)
    pyautogui.typewrite('passenger01', interval=0.08)
    capture_frames(0.5)

    # Click Password field
    pyautogui.click(center_x, center_y + 80)
    pyautogui.typewrite('pass123', interval=0.08)
    capture_frames(0.5)

    # Click 'Sign In to IRCTC'
    pyautogui.click(center_x, center_y + 175)
    capture_frames(3.0)  # Shows Dashboard hydrating

    print(">>> Recording Part 3: Live Broadcast Simulation & AI Assistant...")
    # Click orange '📡 Broadcast Alert' button in the header banner
    pyautogui.click(center_x + 310, center_y - 250)
    capture_frames(2.0)

    # Ask the AI RailSahayak Assistant
    pyautogui.click(center_x - 180, center_y + 60)
    pyautogui.typewrite("Will waitlist clear?", interval=0.05)
    pyautogui.press('enter')
    capture_frames(2.5)

    print(">>> Recording Part 4: Train Ticket Booking Flow...")
    # Click '⚡ Book Train Ticket' shortcut
    pyautogui.click(center_x - 220, center_y - 80)
    capture_frames(2.0)

    # Search & select coach class / seats
    pyautogui.press('tab')
    pyautogui.press('enter')
    capture_frames(3.0)

    print(">>> Recording Part 5: Bookings Portfolio & Cancellation...")
    # Navigate to My Bookings tab
    pyautogui.click(center_x - 10, center_y - 325)
    capture_frames(2.5)

    # Click Cancel Booking button if available
    pyautogui.press('tab')
    capture_frames(2.0)

    # Logout to return to Login Screen
    pyautogui.click(SCREEN_SIZE.width - 80, center_y - 325)
    capture_frames(2.0)

    print(">>> Recording Part 6: Admin Login & Console Inspection...")
    # Enter admin credentials
    pyautogui.click(center_x, center_y + 15)
    pyautogui.hotkey('ctrl', 'a')
    pyautogui.typewrite('admin', interval=0.08)

    pyautogui.click(center_x, center_y + 80)
    pyautogui.hotkey('ctrl', 'a')
    pyautogui.typewrite('admin123', interval=0.08)

    # Select Admin role from combobox
    pyautogui.click(center_x + 50, center_y + 130)
    pyautogui.press('down')
    pyautogui.press('enter')
    capture_frames(0.5)

    # Click Sign In
    pyautogui.click(center_x, center_y + 175)
    capture_frames(3.0)

finally:
    out.release()
    client_proc.terminate()
    print(f"\n[DONE] Demo video saved successfully as: {OUT_FILENAME}")