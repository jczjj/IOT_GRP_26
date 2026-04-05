import os
import time
import shutil
import logging
import requests
from datetime import datetime

# V12.1 Node 0 Monitor & Archiver
REC_DIR = "/home/sdn_service/poc/file_transfer/receive"
ARC_DIR = "/home/sdn_service/poc/file_transfer/archive"
LOG = "/home/sdn_service/poc/python_script/production.log"

# Dashboard endpoint for immediate image ingestion after archive
DASHBOARD_PUSH_URL = os.environ.get("DASHBOARD_PUSH_URL", "http://127.0.0.1:8080/api/image-bridge/push")
NODE_DEVICE_ID = os.environ.get("NODE_DEVICE_ID", "").strip()

logging.basicConfig(filename=LOG, level=logging.INFO, format='[%(asctime)s] %(message)s')


def push_archived_image(dest_path, archive_name):
    """Best-effort webhook push to dashboard backend."""
    payload = {"source_file": archive_name}
    if NODE_DEVICE_ID:
        payload["device_id"] = NODE_DEVICE_ID

    with open(dest_path, "rb") as f:
        files = {"image": (archive_name, f, "application/octet-stream")}
        resp = requests.post(DASHBOARD_PUSH_URL, data=payload, files=files, timeout=8)

    if resp.status_code == 200:
        logging.info(f"📨 PUSHED: {archive_name} to dashboard endpoint.")
    else:
        logging.warning(f"⚠ PUSH FAILED: {archive_name} status={resp.status_code} body={resp.text[:200]}")

def main():
    logging.info("🏁 Node 0 Monitor V12.1 Active (Archive Mode).")
    
    while True:
        target_img = os.path.join(REC_DIR, "gatita.png")
        lock_file = os.path.join(REC_DIR, "payload.lock")

        # Wait for both files to ensure transfer is 100% complete
        if os.path.exists(target_img) and os.path.exists(lock_file):
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            archive_name = f"gatita_{timestamp}.png"
            dest_path = os.path.join(ARC_DIR, archive_name)

            try:
                # Move the image with the new timestamped name
                shutil.move(target_img, dest_path)
                # Delete the lockfile so we don't trigger again
                os.remove(lock_file)
                
                logging.info(f"🎯 ARCHIVED: {archive_name} moved to archive.")
                try:
                    push_archived_image(dest_path, archive_name)
                except Exception as push_exc:
                    logging.error(f"❌ PUSH EXCEPTION: {push_exc}")
            except Exception as e:
                logging.error(f"❌ ARCHIVE FAILED: {e}")

        time.sleep(2)

if __name__ == "__main__":
    main()
