"""Alembic command shortcuts for uv scripts."""

import sys
import subprocess
from pathlib import Path

# Get the path to alembic.ini
ALEMBIC_INI = Path(__file__).parent / "alembic.ini"


def run_alembic(args: list[str]):
    """Run alembic command with config file."""
    cmd = ["alembic", "-c", str(ALEMBIC_INI)] + args
    return subprocess.call(cmd)


def upgrade():
    """Upgrade database to latest migration."""
    print("Running migrations...")
    return run_alembic(["upgrade", "head"])


def downgrade():
    """Downgrade database by one migration."""
    print("Rolling back one migration...")
    return run_alembic(["downgrade", "-1"])


def make_migration():
    """Create a new migration based on model changes."""
    if len(sys.argv) < 2:
        print("Usage: uv run make-migration 'migration message'")
        return 1
    
    message = " ".join(sys.argv[1:])
    print(f"Creating migration: {message}")
    return run_alembic(["revision", "--autogenerate", "-m", message])


def history():
    """Show migration history."""
    return run_alembic(["history"])


def current():
    """Show current migration version."""
    return run_alembic(["current"])


if __name__ == "__main__":
    # For testing
    history()