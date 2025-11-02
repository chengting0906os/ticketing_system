#!/usr/bin/env python3
"""
Aurora Database Inspection Tool

This script connects to Aurora PostgreSQL and provides various observation capabilities:
- List all tables with row counts
- Show table schemas
- Check migration status
- Query specific tables

Usage:
    # List all tables
    PYTHONPATH=. uv run python deployment/script/aurora_inspect.py list

    # Show table schema
    PYTHONPATH=. uv run python deployment/script/aurora_inspect.py schema events

    # Show migration status
    PYTHONPATH=. uv run python deployment/script/aurora_inspect.py migrations

    # Query table data (with limit)
    PYTHONPATH=. uv run python deployment/script/aurora_inspect.py query events --limit 10

    # Show all table schemas
    PYTHONPATH=. uv run python deployment/script/aurora_inspect.py schema-all
"""

import asyncio
import json
import sys
from typing import Any

import asyncpg
import boto3
from rich.console import Console
from rich.table import Table

console = Console()


async def get_db_credentials() -> dict[str, Any]:
    """Get Aurora credentials from AWS Secrets Manager."""
    console.print('🔐 Fetching Aurora credentials from Secrets Manager...', style='yellow')

    client = boto3.client('secretsmanager', region_name='us-west-2')
    response = client.get_secret_value(SecretId='ticketing/aurora/credentials')
    creds = json.loads(response['SecretString'])

    console.print('✅ Credentials retrieved successfully', style='green')
    return creds


async def create_connection() -> asyncpg.Connection:
    """Create connection to Aurora PostgreSQL."""
    creds = await get_db_credentials()

    console.print(f'🔌 Connecting to {creds["host"]}...', style='yellow')

    conn = await asyncpg.connect(
        host=creds['host'],
        port=creds['port'],
        database=creds['dbname'],
        user=creds['username'],
        password=creds['password'],
    )

    console.print('✅ Connected to Aurora PostgreSQL', style='green')
    return conn


async def list_tables(conn: asyncpg.Connection) -> None:
    """List all tables with row counts."""
    console.print('\n📋 Listing all tables...\n', style='bold cyan')

    # Get all tables
    tables = await conn.fetch(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
        ORDER BY table_name;
    """
    )

    if not tables:
        console.print('❌ No tables found. Database might not be migrated yet.', style='red')
        return

    # Create rich table
    table = Table(title='Database Tables', show_header=True, header_style='bold magenta')
    table.add_column('Table Name', style='cyan', no_wrap=True)
    table.add_column('Row Count', justify='right', style='yellow')
    table.add_column('Size', justify='right', style='green')

    for record in tables:
        table_name = record['table_name']

        # Get row count
        count_result = await conn.fetchval(f'SELECT COUNT(*) FROM "{table_name}"')

        # Get table size
        size_result = await conn.fetchval(
            f"""
            SELECT pg_size_pretty(pg_total_relation_size('"{table_name}"'))
        """
        )

        table.add_row(table_name, str(count_result), str(size_result))

    console.print(table)


async def show_table_schema(conn: asyncpg.Connection, table_name: str) -> None:
    """Show schema for a specific table."""
    console.print(f'\n📐 Schema for table: {table_name}\n', style='bold cyan')

    columns = await conn.fetch(
        """
        SELECT
            column_name,
            data_type,
            character_maximum_length,
            is_nullable,
            column_default
        FROM information_schema.columns
        WHERE table_name = $1 AND table_schema = 'public'
        ORDER BY ordinal_position;
    """,
        table_name,
    )

    if not columns:
        console.print(f"❌ Table '{table_name}' not found", style='red')
        return

    # Create rich table
    table = Table(show_header=True, header_style='bold magenta', title=f'Schema: {table_name}')
    table.add_column('Column Name', style='cyan')
    table.add_column('Data Type', style='yellow')
    table.add_column('Nullable', style='green')
    table.add_column('Default', style='blue')

    for col in columns:
        data_type = col['data_type']
        if col['character_maximum_length']:
            data_type += f'({col["character_maximum_length"]})'

        table.add_row(
            col['column_name'],
            data_type,
            'YES' if col['is_nullable'] == 'YES' else 'NO',
            str(col['column_default']) if col['column_default'] else '',
        )

    console.print(table)


async def show_all_schemas(conn: asyncpg.Connection) -> None:
    """Show schemas for all tables."""
    tables = await conn.fetch(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
        ORDER BY table_name;
    """
    )

    for record in tables:
        await show_table_schema(conn, record['table_name'])
        console.print()  # Empty line between tables


async def check_migrations(conn: asyncpg.Connection) -> None:
    """Check Alembic migration status."""
    console.print('\n🔄 Checking migration status...\n', style='bold cyan')

    # Check if alembic_version table exists
    table_exists = await conn.fetchval(
        """
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name = 'alembic_version'
        );
    """
    )

    if not table_exists:
        console.print('❌ Alembic version table not found. Database not migrated yet!', style='red')
        return

    # Get current version
    version = await conn.fetchrow('SELECT * FROM alembic_version;')

    if version:
        table = Table(title='Migration Status', show_header=True, header_style='bold magenta')
        table.add_column('Current Version', style='green')
        table.add_row(version['version_num'])
        console.print(table)
        console.print('\n✅ Database is migrated', style='green')
    else:
        console.print('⚠️  Alembic table exists but no version found', style='yellow')


async def query_table(conn: asyncpg.Connection, table_name: str, limit: int = 10) -> None:
    """Query data from a specific table."""
    console.print(f'\n🔍 Querying table: {table_name} (limit: {limit})\n', style='bold cyan')

    # Check if table exists
    table_exists = await conn.fetchval(
        """
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name = $1
        );
    """,
        table_name,
    )

    if not table_exists:
        console.print(f"❌ Table '{table_name}' not found", style='red')
        return

    # Get data
    rows = await conn.fetch(f'SELECT * FROM "{table_name}" LIMIT $1', limit)

    if not rows:
        console.print(f"⚠️  Table '{table_name}' is empty", style='yellow')
        return

    # Create rich table
    table = Table(
        title=f'Data from {table_name} (showing {len(rows)} rows)',
        show_header=True,
        header_style='bold magenta',
    )

    # Add columns
    for col_name in rows[0].keys():
        table.add_column(col_name, style='cyan')

    # Add rows
    for row in rows:
        table.add_row(*[str(val) for val in row.values()])

    console.print(table)


async def main() -> None:
    """Main entry point."""
    if len(sys.argv) < 2:
        console.print('❌ Usage: python deployment/script/aurora_inspect.py <command>', style='red')
        console.print('\nAvailable commands:', style='yellow')
        console.print('  list              - List all tables with row counts')
        console.print('  schema <table>    - Show schema for a specific table')
        console.print('  schema-all        - Show schemas for all tables')
        console.print('  migrations        - Check migration status')
        console.print('  query <table>     - Query data from a table (default limit: 10)')
        console.print('  query <table> --limit <n>  - Query with custom limit\n', style='dim')
        sys.exit(1)

    command = sys.argv[1]

    try:
        conn = await create_connection()

        if command == 'list':
            await list_tables(conn)

        elif command == 'schema':
            if len(sys.argv) < 3:
                console.print(
                    '❌ Usage: python deployment/script/aurora_inspect.py schema <table_name>',
                    style='red',
                )
                sys.exit(1)
            await show_table_schema(conn, sys.argv[2])

        elif command == 'schema-all':
            await show_all_schemas(conn)

        elif command == 'migrations':
            await check_migrations(conn)

        elif command == 'query':
            if len(sys.argv) < 3:
                console.print(
                    '❌ Usage: python deployment/script/aurora_inspect.py query <table_name> [--limit N]',
                    style='red',
                )
                sys.exit(1)

            table_name = sys.argv[2]
            limit = 10

            if len(sys.argv) >= 5 and sys.argv[3] == '--limit':
                limit = int(sys.argv[4])

            await query_table(conn, table_name, limit)

        else:
            console.print(f'❌ Unknown command: {command}', style='red')
            sys.exit(1)

        await conn.close()
        console.print('\n✅ Connection closed', style='green')

    except Exception as e:
        console.print(f'\n❌ Error: {e}', style='red')
        sys.exit(1)


if __name__ == '__main__':
    asyncio.run(main())
