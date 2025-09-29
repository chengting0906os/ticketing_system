from pathlib import Path


# Base directory
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent

# Log directory
LOG_DIR = BASE_DIR / 'logs'

# RocksDB state directory
ROCKSDB_STATE_DIR = BASE_DIR / 'rocksdb_state'
