import os, time, shutil, logging
from datetime import datetime
REC_DIR = "/home/sdn_service/poc/file_transfer/receive"
ARC_DIR = "/home/sdn_service/poc/file_transfer/archive"
while True:
    img = os.path.join(REC_DIR, "gatita.png")
    lock = os.path.join(REC_DIR, "payload.lock")
    if os.path.exists(img) and os.path.exists(lock):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        shutil.move(img, os.path.join(ARC_DIR, f"gatita_{ts}.png"))
        os.remove(lock)
    time.sleep(2)