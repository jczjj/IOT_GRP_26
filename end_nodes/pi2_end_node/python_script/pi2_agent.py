import serial, time, subprocess, glob, datetime

LOG_FILE = "node_agent.log"

def log(message):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted_msg = f"[{timestamp}] {message}"
    print(formatted_msg)
    with open(LOG_FILE, "a") as f:
        f.write(formatted_msg + "\n")

def get_serial():
    with open('/proc/cpuinfo', 'r') as f:
        for line in f:
            if line.startswith('Serial'): return line.split(':')[1].strip()
    return "UNK"

def start_mission():
    my_id = get_serial()
    ports = glob.glob('/dev/ttyACM*') + glob.glob('/dev/ttyUSB*')
    if not ports:
        log("ERROR: No Arduino detected on Pi 2.")
        return

    try:
        with serial.Serial(ports[0], 9600, timeout=1) as ser:
            time.sleep(2) # Arduino Reset
            log(f"--- NODE AGENT ONLINE ({my_id}) ---")
            ser.write(f"{my_id}\n".encode())
            log("STATUS: Hardware ID broadcasted. Awaiting SDN trigger...")

            while True:
                if ser.in_waiting > 0:
                    line = ser.readline().decode('utf-8', errors='ignore').strip()
                    if "TRIGGER:ASSIGN_02" in line:
                        log("ACTION: SDN Trigger Received. Pivoting to Wi-Fi...")
                        break
            

			# Execute Pivot
            log("NETWORK: Executing pp.sh and pushing data...")
            result = subprocess.run(["bash", "/home/lly_pi2/poc/file_transfer/pp.sh"], capture_output=True, text=True)
            
            # Check if the Bash script actually succeeded
            if result.returncode == 0:
                log("MISSION: gatita.png pushed to Pi 1 successfully.")
            else:
                log("MISSION FAILED: Check test_evidence.log for details.")
                # Optional: log the error from bash
                log(f"DEBUG: {result.stderr}")			
            
    except Exception as e:
        log(f"CRITICAL ERROR: {str(e)}")

if __name__ == "__main__":
    start_mission()
