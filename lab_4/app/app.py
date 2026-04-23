import os
import time
from dataclasses import dataclass
from datetime import date

import psycopg2
from psycopg2.extras import RealDictCursor


@dataclass(frozen=True)
class ShardConfig:
    name: str
    write_host: str
    read_host: str


DB_USER = os.getenv("DB_USER", "wallet")
DB_PASSWORD = os.getenv("DB_PASSWORD", "wallet")
DB_NAME = os.getenv("DB_NAME", "walletdb")
DB_PORT = int(os.getenv("DB_PORT", "5432"))

SHARDS = [
    ShardConfig(
        name="shard_1",
        write_host=os.getenv("SHARD1_PRIMARY_HOST", "localhost"),
        read_host=os.getenv("SHARD1_REPLICA_HOST", "localhost"),
    ),
    ShardConfig(
        name="shard_2",
        write_host=os.getenv("SHARD2_PRIMARY_HOST", "localhost"),
        read_host=os.getenv("SHARD2_REPLICA_HOST", "localhost"),
    ),
]


def connect(host: str):
    return psycopg2.connect(
        host=host,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
    )


def wait_for_db(host: str, max_attempts: int = 30, sleep_seconds: int = 2):
    for attempt in range(1, max_attempts + 1):
        try:
            conn = connect(host)
            conn.close()
            print(f"DB is ready: {host}")
            return
        except Exception as error:
            if attempt == max_attempts:
                raise RuntimeError(f"DB {host} is not ready: {error}") from error
            print(f"Waiting for {host} ({attempt}/{max_attempts})...")
            time.sleep(sleep_seconds)


def shard_for_user(user_id: int) -> ShardConfig:
    return SHARDS[user_id % len(SHARDS)]


def ensure_schema(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id BIGINT PRIMARY KEY,
                full_name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS accounts (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                account_name TEXT NOT NULL,
                balance NUMERIC(12,2) NOT NULL DEFAULT 0,
                UNIQUE (user_id, account_name)
            );
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS categories (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                category_name TEXT NOT NULL,
                kind TEXT NOT NULL CHECK (kind IN ('income', 'expense')),
                UNIQUE (user_id, category_name, kind)
            );
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS transactions (
                transaction_id BIGINT GENERATED ALWAYS AS IDENTITY,
                user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                account_id BIGINT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                category_id BIGINT NOT NULL REFERENCES categories(id) ON DELETE RESTRICT,
                amount NUMERIC(12,2) NOT NULL,
                note TEXT,
                transaction_date DATE NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (transaction_id, transaction_date)
            ) PARTITION BY RANGE (transaction_date);
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS transactions_default
            PARTITION OF transactions DEFAULT;
            """
        )

        first_day = date.today().replace(day=1)
        if first_day.month == 12:
            next_month = first_day.replace(year=first_day.year + 1, month=1)
        else:
            next_month = first_day.replace(month=first_day.month + 1)

        partition_name = f"transactions_{first_day.strftime('%Y_%m')}"
        cur.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {partition_name}
            PARTITION OF transactions
            FOR VALUES FROM (%s) TO (%s);
            """,
            (first_day, next_month),
        )

        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_transactions_user_date
            ON transactions (user_id, transaction_date);
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_user_aggregates (
                user_id BIGINT NOT NULL,
                day DATE NOT NULL,
                total_income NUMERIC(14,2) NOT NULL DEFAULT 0,
                total_expense NUMERIC(14,2) NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, day)
            );
            """
        )

    conn.commit()


def seed_user_data(write_conn, user_id: int, full_name: str):
    email = f"user{user_id}@mail.local"

    with write_conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            INSERT INTO users (id, full_name, email)
            VALUES (%s, %s, %s)
            ON CONFLICT (id) DO UPDATE
                SET full_name = EXCLUDED.full_name,
                    email = EXCLUDED.email;
            """,
            (user_id, full_name, email),
        )

        cur.execute(
            """
            INSERT INTO accounts (user_id, account_name, balance)
            VALUES (%s, 'Main account', 0)
            ON CONFLICT (user_id, account_name) DO NOTHING
            RETURNING id;
            """,
            (user_id,),
        )
        row = cur.fetchone()
        if row:
            account_id = row["id"]
        else:
            cur.execute(
                "SELECT id FROM accounts WHERE user_id = %s AND account_name = 'Main account';",
                (user_id,),
            )
            account_id = cur.fetchone()["id"]

        cur.execute(
            """
            INSERT INTO categories (user_id, category_name, kind)
            VALUES (%s, 'Salary', 'income')
            ON CONFLICT (user_id, category_name, kind) DO NOTHING
            RETURNING id;
            """,
            (user_id,),
        )
        row = cur.fetchone()
        if row:
            salary_category_id = row["id"]
        else:
            cur.execute(
                """
                SELECT id
                FROM categories
                WHERE user_id = %s AND category_name = 'Salary' AND kind = 'income';
                """,
                (user_id,),
            )
            salary_category_id = cur.fetchone()["id"]

        cur.execute(
            """
            INSERT INTO categories (user_id, category_name, kind)
            VALUES (%s, 'Food', 'expense')
            ON CONFLICT (user_id, category_name, kind) DO NOTHING
            RETURNING id;
            """,
            (user_id,),
        )
        row = cur.fetchone()
        if row:
            food_category_id = row["id"]
        else:
            cur.execute(
                """
                SELECT id
                FROM categories
                WHERE user_id = %s AND category_name = 'Food' AND kind = 'expense';
                """,
                (user_id,),
            )
            food_category_id = cur.fetchone()["id"]

        cur.execute(
            """
            INSERT INTO transactions (
                user_id,
                account_id,
                category_id,
                amount,
                note,
                transaction_date
            )
            VALUES
                (%s, %s, %s, 120000.00, 'Monthly salary', CURRENT_DATE),
                (%s, %s, %s, -3500.00, 'Supermarket', CURRENT_DATE);
            """,
            (user_id, account_id, salary_category_id, user_id, account_id, food_category_id),
        )

        cur.execute(
            """
            INSERT INTO daily_user_aggregates (user_id, day, total_income, total_expense)
            VALUES (%s, CURRENT_DATE, 120000.00, 3500.00)
            ON CONFLICT (user_id, day) DO UPDATE
                SET total_income = daily_user_aggregates.total_income + EXCLUDED.total_income,
                    total_expense = daily_user_aggregates.total_expense + EXCLUDED.total_expense;
            """,
            (user_id,),
        )

    write_conn.commit()


def wait_for_replica_data(read_conn, user_id: int, max_attempts: int = 10, sleep_seconds: int = 1):
    query = "SELECT COUNT(*) FROM transactions WHERE user_id = %s;"

    for _ in range(max_attempts):
        try:
            with read_conn.cursor() as cur:
                cur.execute(query, (user_id,))
                count = cur.fetchone()[0]
                if count > 0:
                    return count
        except psycopg2.Error:
            read_conn.rollback()
        time.sleep(sleep_seconds)

    return 0


def read_user_report(read_conn, user_id: int):
    try:
        with read_conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT
                    user_id,
                    COUNT(*) AS tx_count,
                    SUM(amount) AS net_amount
                FROM transactions
                WHERE user_id = %s
                  AND transaction_date >= date_trunc('month', CURRENT_DATE)::date
                GROUP BY user_id;
                """,
                (user_id,),
            )
            tx_stats = cur.fetchone()

            cur.execute(
                """
                SELECT total_income, total_expense
                FROM daily_user_aggregates
                WHERE user_id = %s AND day = CURRENT_DATE;
                """,
                (user_id,),
            )
            daily_stats = cur.fetchone()
        return tx_stats, daily_stats
    except psycopg2.Error:
        read_conn.rollback()
        return None, None


def main():
    print("=== LAB 4: partitioning + sharding + replication ===")

    hosts = []
    for shard in SHARDS:
        hosts.append(shard.write_host)
        hosts.append(shard.read_host)

    for host in hosts:
        wait_for_db(host)

    write_connections = {}
    read_connections = {}

    for shard in SHARDS:
        write_connections[shard.name] = connect(shard.write_host)
        read_connections[shard.name] = connect(shard.read_host)

    try:
        for shard in SHARDS:
            ensure_schema(write_connections[shard.name])
            print(f"Schema is ready on {shard.name}")

        users = [
            (1, "Alice Ivanova"),
            (2, "Bob Petrov"),
            (3, "Olga Sidorova"),
            (4, "Maksim Smirnov"),
        ]

        for user_id, full_name in users:
            shard = shard_for_user(user_id)
            seed_user_data(write_connections[shard.name], user_id, full_name)
            print(f"User {user_id} routed to {shard.name} (write)")

        print("\nRead reports from replicas:")
        for user_id, _ in users:
            shard = shard_for_user(user_id)
            replica_conn = read_connections[shard.name]
            rows = wait_for_replica_data(replica_conn, user_id)
            tx_stats, daily_stats = read_user_report(replica_conn, user_id)

            print(
                f"user={user_id} shard={shard.name} replica_rows={rows} "
                f"tx_stats={tx_stats} daily={daily_stats}"
            )

        print("\nLab 4 demo finished successfully.")

    finally:
        for conn in write_connections.values():
            conn.close()
        for conn in read_connections.values():
            conn.close()


if __name__ == "__main__":
    main()
