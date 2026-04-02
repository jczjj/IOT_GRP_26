#!/usr/bin/env python3
# VERSION: 15.18 (Deadman's Switch)
import serial
import subprocess
import time
import os
import shutil
import yaml
import logging
import argparse
import sys

# --- CONFIGURATION ---
CONFIG_PATH = "/home/sdn_service/poc/python_script/sdn_config.yaml"
BUSY_LOCK = "/tmp/sdn_busy"
MISSION_TIMEOUT = 300  # 5 Minutes total per mission
CMD_TIMEOUT = 120      # 2 Minutes per bash command (pp.sh)

def load_config():
    with open(CONFIG_PATH, 'r') as f: return yaml.safe_load(f)

def set_mission_lock(state):
    """Signals to failsafe.sh whether the system is busy."""
    if state:
        with open(BUSY_LOCK, 'a'): os.utime(BUSY_LOCK, None)
        logging.info("🔒 LOCK: Mission Busy.")
    else:
        if os.path.exists(BUSY_LOCK):
            os.remove(BUSY_LOCK)
            logging.info("🔓 LOCK: Released.")

def run_engine(mode, my_id, target_id, cfg):
    """Executes pp.sh with a hard timeout to prevent hanging."""
    logging.info(f"⚙️ Engine Start: {mode}")
    try:
        subprocess.run([
            "bash", cfg['paths']['engine_path'], mode, str(my_id), str(target_id), 
            cfg['credentials']['home_ssid'], cfg['credentials']['home_pass'], 
            cfg['paths']['log_file']
        ], timeout=CMD_TIMEOUT, check=True)
    except subprocess.TimeoutExpired:
        logging.error(f"⏰ CRITICAL: {mode} command timed out after {CMD_TIMEOUT}s")
        raise  # Pass up to mission handler

def purge_receive(cfg):
    rx_dir = cfg['paths']['receive_dir']
    if not os.path.exists(rx_dir): os.makedirs(rx_dir)
    for f in os.listdir(rx_dir):
        path = os.path.join(rx_dir, f)
        try:
            if os.path.isfile(path): os.unlink(path)
            elif os.path.isdir(path): shutil.rmtree(path)
        except: pass

def process_mission(p, cfg):
    """Handles mission with a global timeout watchdog."""
    start_time = time.time()
    set_mission_lock(True)
    
    try:
        my_id, is_source = p[1], p[2]
        target_id = my_id - 1
        rx_dir = cfg['paths']['receive_dir']
        lock_path = os.path.join(rx_dir, cfg['paths']['lock_file'])
        
        purge_receive(cfg)
        
        if is_source == 1:
            logging.info(f"🚀 SOURCE (Node {my_id})")
            src_image = os.path.join(cfg['paths']['source_dir'], cfg['paths']['payload_file'])
            if os.path.exists(src_image):
                shutil.copy(src_image, rx_dir)
                open(lock_path, 'a').close() 
                run_engine("PIVOT", my_id, target_id, cfg)
            else:
                logging.error("❌ Payload missing!")
        else:
            logging.info(f"📡 RELAY (Node {my_id})")
            run_engine("HOST", my_id, target_id, cfg)
            
            # THE WATCHDOG LOOP
            logging.info(f"⏳ Waiting for data (Timeout: {MISSION_TIMEOUT}s)...")
            while not os.path.exists(lock_path):
                if time.time() - start_time > MISSION_TIMEOUT:
                    logging.error("💥 MISSION TIMEOUT: Data never arrived. Aborting.")
                    raise TimeoutError("Mission exceeded duration limit.")
                time.sleep(2)
                
            logging.info("📦 DATA RECEIVED. Forwarding...")
            run_engine("PIVOT", my_id, target_id, cfg)
        
        purge_receive(cfg)
        logging.info("✅ Mission Finished Successfully.")

    except Exception as e:
        logging.error(f"❌ MISSION ABORTED: {e}")
    finally:
        # Crucial: This ensures Failsafe can recover the node if we fail
        set_mission_lock(False)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sim", nargs=2, type=int)
    args = parser.parse_args()
    
    cfg = load_config()
    logging.basicConfig(filename=cfg['paths']['log_file'], level=logging.INFO, 
                        format='[%(asctime)s] %(levelname)s: %(message)s')

    if args.sim:
        process_mission([0x02, args.sim[0], args.sim[1]], cfg)
        sys.exit(0)

    ser_port = '/dev/ttyUSB0' if os.path.exists('/dev/ttyUSB0') else '/dev/ttyACM0'
    try:
        with serial.Serial(ser_port, 9600, timeout=1) as ser:
            logging.info(f"📻 Listening for LoRa on {ser_port}...")
            while True:
                if ser.in_waiting >= 3:
                    p = list(ser.read(3))
                    if p[0] == 0x02:
                        process_mission(p, cfg)
                time.sleep(0.1)
    except Exception as e:
        logging.error(f"Listener Crash: {e}")

if __name__ == "__main__":
    main()
