import serial, time, subprocess, glob, datetime, os

LOG_FILE = "sdn_controller.log"
TARGET_FILE = os.path.expanduser("~/received_data/gatita.png")

def log(message):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted_msg = f"[{timestamp}] {message}"
    print(formatted_msg)
    with open(LOG_FILE, "a") as f:
        f.write(formatted_msg + "\n")

def check_file_arrival(timeout=60):
    """Watches the received_data folder for the image arrival."""
    log(f"VERIFICATION: Watching for {TARGET_FILE}...")
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        if os.path.exists(TARGET_FILE):
            size = os.path.getsize(TARGET_FILE)
            log(f"SUCCESS: {os.path.basename(TARGET_FILE)} received! Size: {size} bytes.")
            return True
        time.sleep(2)
    
    log("TIMEOUT: File did not arrive within 60 seconds.")
    return False

def start_controller():
    # Pre-run Cleanup
    subprocess.run(["sudo", "fuser", "-k", "8000/tcp"], capture_output=True)
    if os.path.exists(TARGET_FILE):
        os.remove(TARGET_FILE) # Clear old test files
    
    ports = glob.glob('/dev/ttyACM*') + glob.glob('/dev/ttyUSB*')
    if not ports:
        log("ERROR: No Arduino detected.")
        return

    try:
        with serial.Serial(ports[0], 9600, timeout=1) as ser:
            log("--- PI 1: SDN CONTROLLER ONLINE ---")
            
            while True:
                if ser.in_waiting > 0:
                    line = ser.readline().decode('utf-8', errors='ignore').strip()
                    if line.startswith("FOUND_NODE:"):
                        log(f"DISCOVERY: Node {line.split(':')[1]} identified.")
                        ser.write("ASSIGN:02\n".encode())
                        break
            
            # Execute Network Pivot
            log("NETWORK: Pivoting to Hotspot Mode...")
            subprocess.run(["bash", "/home/lly_pi/poc/file_transfer/pp.sh"])
            
            # Start verification
            if check_file_arrival():
                log("MISSION: Complete. File available at http://10.42.1.1:8000")
            else:
                log("MISSION: Failed to receive file.")

            log("--- Press Ctrl+C to Shutdown ---")
            while True: time.sleep(1)
                
    except KeyboardInterrupt:
        log("SHUTDOWN: Cleaning up...")
        subprocess.run(["sudo", "nmcli", "con", "down", "pi_01pi_01"], capture_output=True)
        subprocess.run(["sudo", "fuser", "-k", "8000/tcp"], capture_output=True)

if __name__ == "__main__":
    start_controller()
