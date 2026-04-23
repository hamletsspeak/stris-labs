import json
import os
import threading
import time
from decimal import Decimal

import psycopg
from redis import Redis
from redis.exceptions import RedisError

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "dbname": os.getenv("DB_NAME", "lab2"),
    "user": os.getenv("DB_USER", "lab2"),
    "password": os.getenv("DB_PASSWORD", "lab2"),
}

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))


def get_conn(autocommit: bool = False) -> psycopg.Connection:
    conn = psycopg.connect(**DB_CONFIG)
    conn.autocommit = autocommit
    return conn


def wait_for_services(max_retries: int = 60) -> Redis:
    for _ in range(max_retries):
        try:
            with get_conn(autocommit=True) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
            redis_client = Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
            redis_client.ping()
            return redis_client
        except Exception:
            time.sleep(1)
    raise RuntimeError("PostgreSQL/Redis are not ready")


def reset_schema() -> None:
    with get_conn(autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS users")
            cur.execute("DROP TABLE IF EXISTS accounts")


def print_header(title: str) -> None:
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)


def parse_explain_plan(plan_row: object) -> dict:
    # EXPLAIN ... FORMAT JSON returns a single-element list with plan metadata.
    if isinstance(plan_row, list):
        return plan_row[0]
    return json.loads(plan_row)[0]


def run_explain(email: str) -> dict:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
                SELECT * FROM users WHERE email = %s
                """,
                (email,),
            )
            result = cur.fetchone()
            if result is None:
                raise RuntimeError("EXPLAIN returned no rows")
            return parse_explain_plan(result[0])


def part_1_indexes() -> int:
    print_header("PART 1: INDEXES")

    with get_conn(autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE users (
                    id BIGSERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    email TEXT NOT NULL
                )
                """
            )

            cur.execute(
                """
                INSERT INTO users (name, email)
                SELECT
                    'User ' || gs,
                    CASE
                        WHEN gs = 20000 THEN 'target.user@example.com'
                        ELSE 'user' || gs || '@example.com'
                    END
                FROM generate_series(1, 20000) AS gs
                """
            )

    target_email = "target.user@example.com"
    before_index = run_explain(target_email)
    before_plan = before_index["Plan"]

    checked_rows_before = int(before_plan.get("Actual Rows", 0)) + int(
        before_plan.get("Rows Removed by Filter", 0)
    )
    time_before = float(before_index.get("Execution Time", 0.0))

    print("Without index:")
    print(f"  Node type: {before_plan.get('Node Type')}")
    print(f"  Execution time: {time_before:.4f} ms")
    print(f"  Checked rows (approx): {checked_rows_before}")

    with get_conn(autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("CREATE INDEX idx_users_email ON users(email)")

    after_index = run_explain(target_email)
    after_plan = after_index["Plan"]

    checked_rows_after = int(after_plan.get("Actual Rows", 0)) + int(
        after_plan.get("Rows Removed by Filter", 0)
    )
    time_after = float(after_index.get("Execution Time", 0.0))

    print("With index:")
    print(f"  Node type: {after_plan.get('Node Type')}")
    print(f"  Execution time: {time_after:.4f} ms")
    print(f"  Checked rows (approx): {checked_rows_after}")

    if time_after > 0:
        speedup = time_before / time_after
        print(f"Speedup: x{speedup:.2f}")

    return 20000


def get_balances() -> dict[int, Decimal]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, balance FROM accounts ORDER BY id")
            rows = cur.fetchall()
            return {int(account_id): balance for account_id, balance in rows}


def part_2_transactions() -> None:
    print_header("PART 2: TRANSACTIONS AND ROLLBACK (ACID)")

    with get_conn(autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE accounts (
                    id SERIAL PRIMARY KEY,
                    balance NUMERIC(12, 2) NOT NULL
                )
                """
            )
            cur.execute("INSERT INTO accounts (balance) VALUES (1000.00), (1000.00)")

    print(f"Balances before transfer: {get_balances()}")

    try:
        with get_conn() as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE accounts SET balance = balance - 250 WHERE id = 1"
                    )
                    cur.execute(
                        "UPDATE accounts SET balance = balance + 250 WHERE id = 2"
                    )
                    raise RuntimeError("Artificial failure after debit")
    except RuntimeError as exc:
        print(f"Transfer failed intentionally: {exc}")

    print(f"Balances after failed transfer: {get_balances()}")


def isolation_read_committed_demo() -> None:
    print("\nScenario A: READ COMMITTED (non-repeatable read is possible)")

    with get_conn(autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE accounts SET balance = 1000 WHERE id = 1")

    writer_done = threading.Event()

    def writer():
        with get_conn() as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    cur.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
                    cur.execute("UPDATE accounts SET balance = 1200 WHERE id = 1")
            writer_done.set()

    def reader():
        with get_conn() as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    cur.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
                    cur.execute("SELECT balance FROM accounts WHERE id = 1")
                    first = cur.fetchone()[0]
                    writer_done.wait()
                    cur.execute("SELECT balance FROM accounts WHERE id = 1")
                    second = cur.fetchone()[0]
                    print(f"  First read:  {first}")
                    print(f"  Second read: {second}")

    t_reader = threading.Thread(target=reader)
    t_writer = threading.Thread(target=writer)
    t_reader.start()
    time.sleep(0.3)
    t_writer.start()
    t_reader.join()
    t_writer.join()


def isolation_repeatable_read_demo() -> None:
    print("\nScenario B: REPEATABLE READ (snapshot is stable)")

    with get_conn(autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE accounts SET balance = 1000 WHERE id = 1")

    first_read_done = threading.Event()
    writer_done = threading.Event()

    def writer():
        first_read_done.wait()
        with get_conn() as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    cur.execute("UPDATE accounts SET balance = 1400 WHERE id = 1")
        writer_done.set()

    def reader():
        with get_conn() as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
                    cur.execute("SELECT balance FROM accounts WHERE id = 1")
                    first = cur.fetchone()[0]
                    first_read_done.set()
                    writer_done.wait()
                    cur.execute("SELECT balance FROM accounts WHERE id = 1")
                    second = cur.fetchone()[0]
                    print(f"  First read:  {first}")
                    print(f"  Second read: {second}")

    t_reader = threading.Thread(target=reader)
    t_writer = threading.Thread(target=writer)
    t_reader.start()
    t_writer.start()
    t_reader.join()
    t_writer.join()


def part_3_isolation_levels() -> None:
    print_header("PART 3: ISOLATION LEVELS")
    isolation_read_committed_demo()
    isolation_repeatable_read_demo()


def part_4_cache(redis_client: Redis, user_id: int) -> None:
    print_header("PART 4: CACHE ASIDE")

    redis_client.flushdb()
    db_queries = {"count": 0}

    def get_user_with_cache(cache_user_id: int) -> tuple[dict, str]:
        cache_key = f"user:{cache_user_id}"
        try:
            cached_payload = redis_client.get(cache_key)
        except RedisError:
            cached_payload = None

        if cached_payload is not None:
            return json.loads(cached_payload), "cache"

        db_queries["count"] += 1
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, name, email FROM users WHERE id = %s",
                    (cache_user_id,),
                )
                row = cur.fetchone()
                if row is None:
                    raise ValueError(f"User with id={cache_user_id} not found")

        user = {"id": row[0], "name": row[1], "email": row[2]}

        try:
            redis_client.setex(cache_key, 60, json.dumps(user))
        except RedisError:
            pass

        return user, "db"

    first_user, first_source = get_user_with_cache(user_id)
    print(f"First request source:  {first_source}")
    print(f"First request payload: {first_user}")

    second_user, second_source = get_user_with_cache(user_id)
    print(f"Second request source: {second_source}")
    print(f"Second request payload: {second_user}")

    print(f"DB was queried {db_queries['count']} time(s)")


def main() -> None:
    redis_client = wait_for_services()
    reset_schema()

    sample_user_id = part_1_indexes()
    part_2_transactions()
    part_3_isolation_levels()
    part_4_cache(redis_client, sample_user_id)

    print_header("DONE")
    print("All lab scenarios finished successfully.")


if __name__ == "__main__":
    main()
