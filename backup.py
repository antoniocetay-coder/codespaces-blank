import os
import shutil

from datetime import datetime

from config import *

BACKUP_DIR = "backups"

def criar_backup():

    print("BACKUP EXECUTOU")

    os.makedirs(
        BACKUP_DIR,
        exist_ok=True
    )

    hoje = datetime.now().strftime(
        "%Y-%m-%d"
    )

    backup_path = os.path.join(
        BACKUP_DIR,
        f"backup_{hoje}.db"
    )

    if os.path.exists(backup_path):
        return

    shutil.copy2(
        DB_PATH,
        backup_path
    )

    print(f"Backup criado: {backup_path}")