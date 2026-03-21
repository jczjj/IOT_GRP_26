import serial, subprocess, time, os, shutil, yaml, logging, sys, argparse

CONFIG_PATH = "/home/sdn_service/poc/python_script/sdn_config.yaml"

def setup_logging(log_path):
    logging.basicConfig(filename=log_path, level=logging.INFO, format='[%(asctime)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

def load_config():
    with open(CONFIG_PATH, 'r') as f: return yaml.safe_load(f)

def call_engine(mode, my_id, target_id, cfg):
    subprocess.run(["bash", cfg['paths']['script_path'], mode, str(my_id), str(target_id), cfg['credentials']['pc_ssid'], cfg['credentials']['pc_pass'], str(cfg['network']['recovery_enabled']).lower(), cfg['paths']['receive_dir'], cfg['paths']['log_file']])

def cleanup_staging(path):
    if os.path.exists(path):
        count = 0
        for item in os.listdir(path):
            ipath = os.path.join(path, item)
            try:
                if os.path.isfile(ipath): os.unlink(ipath); count += 1
                elif os.path.isdir(ipath): shutil.rmtree(ipath); count += 1
            except Exception as e: logging.error(f"Cleanup error: {e}")
        logging.info(f"🧹 Staging area cleaned. {count} items removed.")

def process_logic(p, cfg):
    my_id, is_source = p[1], p[2]
    target_id = my_id - 1
    logging.info(f"🎯 EXECUTE: Node {my_id} -> {target_id} | Source={is_source}")
    
    if is_source == 0:
        cleanup_staging(cfg['paths']['receive_dir'])
        call_engine("HOST", my_id, target_id, cfg)
        lock_path = os.path.join(cfg['paths']['receive_dir'], cfg['paths']['lock_file'])
        logging.info(f"⏳ Waiting for payload... Looking for: {lock_path}")
        
        last_log = time.time()
        while not os.path.exists(lock_path):
            if time.time() - last_log > 30:
                logging.info(f"Still waiting. Current files: {os.listdir(cfg['paths']['receive_dir'])}")
                last_log = time.time()
            time.sleep(1)
        
        if os.path.exists('/tmp/sdn_busy'):
            os.remove('/tmp/sdn_busy')
            logging.info("🔒 Lock detected! System Unlocked. Proceeding to PIVOT.")
    
    call_engine("PIVOT", my_id, target_id, cfg)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sim", nargs=2, type=int)
    args = parser.parse_args(); cfg = load_config(); setup_logging(cfg['paths']['log_file'])

    if args.sim:
        process_logic([0x02, args.sim[0], args.sim[1]], cfg); sys.exit(0)

    ser_port = '/dev/ttyUSB0' if os.path.exists('/dev/ttyUSB0') else '/dev/ttyACM0'
    if not os.path.exists(ser_port):
        logging.info("🏁 Passive Mode Active.")
        while True: time.sleep(3600)

    try:
        with serial.Serial(ser_port, 9600, timeout=1) as ser:
            logging.info(f"🤖 Agent V12.4 Ready on {ser_port}.")
            while True:
                if ser.in_waiting >= 3:
                    p = list(ser.read(3))
                    if p[0] == 0x02: process_logic(p, cfg)
                time.sleep(0.1)
    except Exception as e:
        logging.error(f"💥 Agent Error: {e}")
    finally:
        if os.path.exists('/tmp/sdn_busy'): os.remove('/tmp/sdn_busy')

if __name__ == "__main__": main()