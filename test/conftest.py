"""
Test Configuration and Fixtures

This module provides:
- ScyllaDB setup and cleanup for parallel testing (pytest-xdist)
- Kvrocks isolation with worker-specific key prefixes
- Test fixtures for users, events, and tickets
- BDD step definitions (imported from bdd_steps_loader.py)
- Service fixtures (imported from fixture_loader.py)

Note: For adding new BDD steps or fixtures, update the respective loader modules
instead of this file to maintain a clean separation of concerns.
"""

import asyncio
import os
from pathlib import Path

from cassandra.auth import PlainTextAuthProvider
from cassandra.cluster import Cluster
from dotenv import load_dotenv
from fastapi.testclient import TestClient
import pytest


# =============================================================================
# Environment Setup for Parallel Testing
# =============================================================================
# Each pytest-xdist worker gets isolated keyspace and Kvrocks namespace
worker_id = os.environ.get('PYTEST_XDIST_WORKER', 'master')
if worker_id == 'master':
    os.environ['SCYLLA_KEYSPACE'] = 'ticketing_system_test'
    os.environ['KVROCKS_KEY_PREFIX'] = 'test_'
else:
    # Worker-specific isolation
    os.environ['SCYLLA_KEYSPACE'] = f'ticketing_system_test_{worker_id}'
    os.environ['KVROCKS_KEY_PREFIX'] = f'test_{worker_id}_'

# Test log directory
test_log_dir = Path(__file__).parent / 'test_log'
test_log_dir.mkdir(exist_ok=True)
os.environ['TEST_LOG_DIR'] = str(test_log_dir)

# =============================================================================
# Import Application and Test Components
# =============================================================================
# Import all BDD steps and service fixtures through consolidated modules
from test.test_main import app  # noqa: E402
from test.bdd_steps_loader import *  # noqa: E402, F403
from test.fixture_loader import *  # noqa: E402, F403

# Explicit imports for commonly used test utilities
from test.shared.utils import create_user  # noqa: E402
from test.test_constants import TEST_TICKET_ID_1  # noqa: E402
from test.util_constant import (  # noqa: E402
    ANOTHER_BUYER_EMAIL,
    ANOTHER_BUYER_NAME,
    DEFAULT_PASSWORD,
    TEST_BUYER_EMAIL,
    TEST_BUYER_NAME,
    TEST_SELLER_EMAIL,
    TEST_SELLER_NAME,
)


# =============================================================================
# ScyllaDB Configuration
# =============================================================================
env_file = '.env' if Path('.env').exists() else '.env.example'
# Load .env but don't override existing environment variables (Docker env has priority)
load_dotenv(env_file, override=False)


def _parse_contact_points(value: str) -> list[str]:
    """Parse SCYLLA_CONTACT_POINTS from env var (supports JSON array or comma-separated)"""
    import json

    try:
        # Try JSON array format: ["host1", "host2"]
        return json.loads(value)
    except (json.JSONDecodeError, ValueError):
        # Fall back to comma-separated: host1,host2
        return [h.strip() for h in value.split(',') if h.strip()]


# Support xdist parallel testing with unique keyspace per worker
def _get_keyspace_name():
    """Get keyspace name (already configured with worker suffix in environment)"""
    # The keyspace name is already set correctly with worker suffix at lines 30-37
    return os.getenv('SCYLLA_KEYSPACE', 'ticketing_system_test')


SCYLLA_CONFIG = {
    'contact_points': _parse_contact_points(os.getenv('SCYLLA_CONTACT_POINTS', 'localhost')),
    'port': int(os.getenv('SCYLLA_PORT', '9042')),
    'username': os.getenv('SCYLLA_USERNAME', 'cassandra'),
    'password': os.getenv('SCYLLA_PASSWORD', 'cassandra'),
    'keyspace': _get_keyspace_name(),
}

# Cache for table names to avoid repeated queries
_cached_tables = None


# =============================================================================
# ScyllaDB Setup and Cleanup
# =============================================================================
def get_scylla_session():
    """Get ScyllaDB session with authentication (test configuration)

    Note: Uses execution profiles with WhiteListRoundRobinPolicy
    to prevent auto-discovery of Docker internal IPs during local testing.
    """
    from cassandra import ConsistencyLevel
    from cassandra.cluster import EXEC_PROFILE_DEFAULT, ExecutionProfile
    from cassandra.policies import WhiteListRoundRobinPolicy

    auth_provider = PlainTextAuthProvider(
        username=SCYLLA_CONFIG['username'], password=SCYLLA_CONFIG['password']
    )

    # Use WhiteList to ONLY connect to localhost (prevent Docker internal IP discovery)
    whitelist_policy = WhiteListRoundRobinPolicy(SCYLLA_CONFIG['contact_points'])

    # Create execution profile matching production configuration
    # This replaces the deprecated load_balancing_policy parameter at Cluster level
    default_profile = ExecutionProfile(
        load_balancing_policy=whitelist_policy,
        consistency_level=ConsistencyLevel.LOCAL_QUORUM,
        request_timeout=30,  # Increased for test stability
    )

    cluster = Cluster(
        contact_points=SCYLLA_CONFIG['contact_points'],
        port=SCYLLA_CONFIG['port'],
        auth_provider=auth_provider,
        protocol_version=4,  # Match production setting
        # Increase timeouts for schema agreement in multi-node cluster
        connect_timeout=30,  # 30 seconds for initial connection
        control_connection_timeout=30,  # 30 seconds for control connection
        max_schema_agreement_wait=60,  # Wait up to 60 seconds for schema agreement
        # Execution profiles (modern API, replaces legacy parameters)
        execution_profiles={EXEC_PROFILE_DEFAULT: default_profile},
    )
    return cluster, cluster.connect()


async def setup_test_database():
    """Create test keyspace and tables for ScyllaDB"""
    cluster, session = get_scylla_session()

    try:
        keyspace = SCYLLA_CONFIG['keyspace']

        # Drop and recreate keyspace for clean state
        session.execute(f'DROP KEYSPACE IF EXISTS {keyspace}')

        # Create keyspace with RF=1 for testing
        session.execute(f"""
            CREATE KEYSPACE IF NOT EXISTS {keyspace}
            WITH REPLICATION = {{
                'class': 'NetworkTopologyStrategy',
                'datacenter1': 1
            }} AND TABLETS = {{'enabled': false}}
        """)

        # Use the keyspace
        session.set_keyspace(keyspace)

        # Load and execute schema from file
        schema_file = (
            Path(__file__).parent.parent / 'src' / 'platform' / 'database' / 'scylla_schemas.cql'
        )
        with open(schema_file, 'r') as f:
            schema_sql = f.read()

        # Remove all comment lines first (lines starting with --)
        lines = schema_sql.split('\n')
        clean_lines = [line for line in lines if not line.strip().startswith('--')]
        schema_sql_clean = '\n'.join(clean_lines)

        # Parse and execute table creation statements (skip keyspace creation)
        statements = [stmt.strip() for stmt in schema_sql_clean.split(';') if stmt.strip()]
        for statement in statements:
            # Skip CREATE KEYSPACE and USE keyspace statements
            if any(keyword in statement.upper() for keyword in ['CREATE KEYSPACE', 'USE ']):
                continue

            # Replace any hardcoded keyspace references
            statement = statement.replace('ticketing_system.', f'{keyspace}.')

            if statement:
                try:
                    session.execute(statement)
                except Exception as e:
                    # Print full statement for debugging
                    print('\n❌ Failed to execute statement:')
                    print(f'Statement: {statement}')
                    print(f'Error: {e}\n')
                    raise  # Re-raise to catch schema errors early

        await verify_tables_created(session)

    finally:
        cluster.shutdown()


async def verify_tables_created(session):
    """Verify all required tables exist"""
    required_tables = ['user', 'event', 'booking', 'ticket']
    keyspace = SCYLLA_CONFIG['keyspace']

    result = session.execute(f"""
        SELECT table_name FROM system_schema.tables
        WHERE keyspace_name = '{keyspace}'
    """)
    existing_tables = [row.table_name for row in result]

    global _cached_tables
    _cached_tables = existing_tables

    missing_tables = [t for t in required_tables if t not in existing_tables]
    if missing_tables:
        raise RuntimeError(
            f'Table creation failed: missing {missing_tables}. Found: {existing_tables}'
        )


async def clean_all_tables():
    """Truncate all tables for test isolation"""
    global _cached_tables
    cluster, session = get_scylla_session()

    try:
        keyspace = SCYLLA_CONFIG['keyspace']
        session.set_keyspace(keyspace)

        # Get table list if not cached
        if _cached_tables is None:
            result = session.execute(f"""
                SELECT table_name FROM system_schema.tables
                WHERE keyspace_name = '{keyspace}'
            """)
            _cached_tables = [row.table_name for row in result]

        # Truncate all tables
        if _cached_tables:
            for table in _cached_tables:
                try:
                    session.execute(f'TRUNCATE {keyspace}.{table}')
                except Exception as e:
                    print(f'Warning: Failed to truncate {table}: {e}')

    finally:
        cluster.shutdown()


# =============================================================================
# Pytest Hooks for Parallel Testing
# =============================================================================
def pytest_configure(config):
    """
    Setup database with file-based locking for parallel testing

    Uses file lock to ensure only ONE process (master or worker)
    creates the database at a time, preventing race conditions
    """

    from filelock import FileLock

    # Use a lock file in the test directory
    lock_file = Path(__file__).parent / '.pytest_scylla_setup.lock'
    lock = FileLock(lock_file, timeout=120)  # 2 minute timeout

    # Each worker gets its own keyspace, so all need to create their keyspace
    worker_id = os.environ.get('PYTEST_XDIST_WORKER', 'master')
    try:
        with lock:
            # Only setup if keyspace doesn't exist yet
            print(f'\n🔧 [{worker_id}] Setting up ScyllaDB keyspace: {SCYLLA_CONFIG["keyspace"]}')
            asyncio.run(setup_test_database())
            print(f'✅ [{worker_id}] ScyllaDB setup complete\n')
    except Exception as e:
        print(f'❌ [{worker_id}] ScyllaDB setup failed: {e}')
        raise


# =============================================================================
# Auto-use Fixtures for Test Isolation
# =============================================================================
@pytest.fixture(autouse=True, scope='function')
async def clean_kvrocks():
    """
    Clean Kvrocks and reset async client before each test

    CRITICAL: Reset async kvrocks_client to prevent event loop contamination.
    The global singleton holds a reference to the first event loop, causing
    "Event loop is closed" errors in subsequent tests if not reset.
    """
    from src.platform.state.kvrocks_client import kvrocks_client, kvrocks_client_sync

    # 1. Disconnect and reset async client (prevents event loop contamination)
    # Note: KvrocksClient now uses per-event-loop clients (_clients dict)
    try:
        await kvrocks_client.disconnect()
    except Exception:
        pass  # Ignore if no client exists for current loop

    # 2. Initialize async client for current event loop
    try:
        await kvrocks_client.initialize()
    except Exception:
        pass  # Ignore if already initialized

    # 3. Clean Kvrocks data using sync client
    key_prefix = os.getenv('KVROCKS_KEY_PREFIX', 'test_')
    sync_client = kvrocks_client_sync.connect()
    keys: list[str] = sync_client.keys(f'{key_prefix}*')  # type: ignore
    if keys:
        sync_client.delete(*keys)

    yield

    # 4. Cleanup after test
    keys_after: list[str] = sync_client.keys(f'{key_prefix}*')  # type: ignore
    if keys_after:
        sync_client.delete(*keys_after)

    # 5. Reset async client again (per-event-loop cleanup)
    try:
        await kvrocks_client.disconnect()
    except Exception:
        pass  # Ignore if no client exists for current loop


@pytest.fixture(autouse=True, scope='function')
async def clean_database():
    """
    Clean all ScyllaDB tables after each test

    Critical for test isolation - ensures each test starts with clean state
    """
    await clean_all_tables()
    yield
    await clean_all_tables()


# =============================================================================
# Session-scoped Fixtures
# =============================================================================
@pytest.fixture(scope='session')
def client():
    """
    FastAPI TestClient for making HTTP requests.

    raise_server_exceptions=False allows catching 500 errors as HTTP responses
    instead of raising exceptions, enabling proper testing of error handling.
    """
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def clear_client_cookies(client):
    """Clear client cookies before/after each test to avoid auth state leakage"""
    client.cookies.clear()
    yield
    client.cookies.clear()


@pytest.fixture(scope='session')
def seller_user(client):
    """Create test seller user"""
    created = create_user(client, TEST_SELLER_EMAIL, DEFAULT_PASSWORD, TEST_SELLER_NAME, 'seller')
    return created or {
        'id': 1,
        'email': TEST_SELLER_EMAIL,
        'name': TEST_SELLER_NAME,
        'role': 'seller',
    }


@pytest.fixture(scope='session')
def buyer_user(client):
    """Create test buyer user"""
    created = create_user(client, TEST_BUYER_EMAIL, DEFAULT_PASSWORD, TEST_BUYER_NAME, 'buyer')
    return created or {
        'id': 2,
        'email': TEST_BUYER_EMAIL,
        'name': TEST_BUYER_NAME,
        'role': 'buyer',
    }


@pytest.fixture(scope='session')
def another_buyer_user(client):
    """Create another test buyer user"""
    created = create_user(
        client, ANOTHER_BUYER_EMAIL, DEFAULT_PASSWORD, ANOTHER_BUYER_NAME, 'buyer'
    )
    return created or {
        'id': 3,
        'email': ANOTHER_BUYER_EMAIL,
        'name': ANOTHER_BUYER_NAME,
        'role': 'buyer',
    }


# =============================================================================
# Unit Test Fixtures
# =============================================================================
@pytest.fixture
def sample_event():
    """Sample event for unit testing"""
    from unittest.mock import Mock

    return Mock(id=1, seller_id=1, name='Test Event')


@pytest.fixture
def available_tickets():
    """Sample available tickets for unit testing"""
    from datetime import datetime

    from src.service.ticketing.domain.aggregate.event_ticketing_aggregate import (
        Ticket,
        TicketStatus,
    )

    now = datetime.now()
    return [
        Ticket(
            id=TEST_TICKET_ID_1,
            event_id=TEST_TICKET_ID_1,
            section='A',
            subsection=1,
            row=1,
            seat=1,
            price=1000,
            status=TicketStatus.AVAILABLE,
            created_at=now,
            updated_at=now,
        )
    ]


@pytest.fixture
def execute_cql_statement():
    """
    Execute SQL statement with PostgreSQL→ScyllaDB translation

    Translates:
    - Named parameters (:param) to positional (%s)
    - Table names: "user"→users, "event"→events, "booking"→bookings, "ticket"→tickets
    - Removes unsupported syntax (RETURNING, setval)
    """
    import re

    def _execute(statement: str, params: dict | None = None, fetch: bool = False):
        if params is None:
            params = {}

        cluster, session = get_scylla_session()
        try:
            keyspace = SCYLLA_CONFIG['keyspace']
            session.set_keyspace(keyspace)

            # No table name translation needed - ScyllaDB uses same singular names as PostgreSQL
            # Tables: "user", "event", "booking", "ticket"

            # Remove RETURNING clause (not supported in ScyllaDB)
            statement = re.sub(r'\s+RETURNING\s+\w+', '', statement, flags=re.IGNORECASE)

            # Remove ON CONFLICT clause (ScyllaDB uses IF NOT EXISTS instead)
            # Handles both: "ON CONFLICT (id) DO NOTHING" and "ON CONFLICT DO NOTHING"
            statement = re.sub(
                r'\s+ON\s+CONFLICT(\s*\([^)]+\))?\s+DO\s+NOTHING',
                '',
                statement,
                flags=re.IGNORECASE,
            )

            # Remove ORDER BY clause (ScyllaDB requires partition key restriction for ORDER BY)
            statement = re.sub(r'\s+ORDER\s+BY\s+[\w\s,]+', '', statement, flags=re.IGNORECASE)

            # Remove setval calls (PostgreSQL sequence management)
            if 'setval' in statement.lower():
                return None

            # Add id to INSERT statements if missing (ScyllaDB requires explicit PRIMARY KEY)
            if re.search(
                r'\bINSERT\s+INTO\s+("?user"?|"?event"?|"?booking"?|"?ticket"?)\s*\(',
                statement,
                flags=re.IGNORECASE,
            ):
                # Check if id is already in the column list (use word boundary to avoid matching buyer_id, event_id, etc.)
                insert_match = re.search(
                    r'\bINSERT\s+INTO\s+"?(\w+)"?\s*\(([^)]+)\)', statement, flags=re.IGNORECASE
                )
                if insert_match and not re.search(
                    r'\bid\b', insert_match.group(2), flags=re.IGNORECASE
                ):
                    # Add id to column list
                    columns = insert_match.group(2)
                    statement = statement.replace(f'({columns})', f'(id, {columns})', 1)

                    # Find VALUES clause and add id placeholder
                    values_match = re.search(r'\bVALUES\s*\(', statement, flags=re.IGNORECASE)
                    if values_match:
                        # Add %s for the generated id
                        statement = statement.replace('VALUES (', 'VALUES (%s, ', 1)
                        # We'll add the id value to param_values later

            # Convert named parameters (:param) to positional (%s) with ordered tuple
            from typing import Any

            param_values: list[Any] = []

            # Check if we added an id to INSERT
            insert_id_added = False  # noqa: F841
            if 'VALUES (%s,' in statement and re.search(
                r'\bINSERT\s+INTO\s+("?user"?|"?event"?|"?booking"?|"?ticket"?)',
                statement,
                flags=re.IGNORECASE,
            ):
                from uuid_utils import uuid7

                generated_id = uuid7()
                param_values.append(generated_id)
                insert_id_added = True  # noqa: F841

            if ':' in statement:
                # Find all :param_name patterns in order
                param_names = re.findall(r':(\w+)', statement)

                # Replace :param_name with %s and preserve UUID objects
                for param_name in param_names:
                    statement = statement.replace(f':{param_name}', '%s', 1)
                    value = params.get(param_name)
                    # UUID objects must be passed as-is to the driver (don't convert to string)
                    param_values.append(value)

            # Translate NOW() to current timestamp
            if 'NOW()' in statement:
                from datetime import datetime, timezone

                now = datetime.now(timezone.utc)
                # Count NOW() occurrences
                now_count = statement.count('NOW()')
                statement = statement.replace('NOW()', '%s')
                # Add now timestamp for each NOW() occurrence
                for _ in range(now_count):
                    param_values.append(now)

            param_tuple = tuple(param_values)

            # Add ALLOW FILTERING for SELECT queries with WHERE clause (ScyllaDB requirement)
            # Only if not already present and it's a SELECT with WHERE
            if re.search(
                r'\bSELECT\b.*\bWHERE\b', statement, flags=re.IGNORECASE | re.DOTALL
            ) and not re.search(r'\bALLOW\s+FILTERING\b', statement, flags=re.IGNORECASE):
                statement = statement.rstrip().rstrip(';') + ' ALLOW FILTERING'

            # Execute query
            result = session.execute(statement, param_tuple)

            if fetch:
                return [dict(row._asdict()) for row in result]
            return None

        finally:
            cluster.shutdown()

    return _execute


# =============================================================================
# Kvrocks Fixtures for Lua Script Tests
# =============================================================================
@pytest.fixture
def kvrocks_client_sync_for_test():
    """
    Sync Kvrocks client for async tests to avoid event loop conflicts

    Uses sync client in async test context to ensure test verification logic
    is independent from the async operations being tested.
    """
    from src.platform.state.kvrocks_client import kvrocks_client_sync

    key_prefix = os.getenv('KVROCKS_KEY_PREFIX', 'test_')

    # Cleanup before test
    client = kvrocks_client_sync.connect()
    keys_before: list[str] = client.keys(f'{key_prefix}*')  # type: ignore
    if keys_before:
        client.delete(*keys_before)

    yield client

    # Cleanup after test
    keys_after: list[str] = client.keys(f'{key_prefix}*')  # type: ignore
    if keys_after:
        client.delete(*keys_after)
