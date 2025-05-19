import os
import psycopg2
from psycopg2 import sql, OperationalError
from contextlib import contextmanager
from typing import Optional, Generator, Dict, List, Any
import json


class PostgresManager:
    def __init__(
            self,
            conn_url=os.environ.get('DATABASE_URL', ''),
            required_schemas=[],
            required_tables={},
            required_functions={}
    ):
        self.db_url = conn_url

        # Initialize database structure
        self.ensure_required_functions(required_functions)
        self.ensure_required_schema(required_schemas, required_tables)

    def ensure_required_functions(self, functions: Dict[str, str]) -> None:
        """Ensures the required functions exist for this object to operate correctly"""
        if not functions:
            return

        with self.get_connection() as conn:
            with conn.cursor() as cur:
                for func_name, func_sql in functions.items():
                    # Check if function exists
                    cur.execute(sql.SQL("""
                        SELECT 1 FROM pg_proc 
                        WHERE proname = %s
                    """), (func_name,))
                    
                    if not cur.fetchone():
                        # Create function if it doesn't exist
                        cur.execute(func_sql)
                        conn.commit()

    def ensure_required_schema(self, schemas: List[str], tables: Dict[str, Dict[str, str]]) -> None:
        """Ensures the required schema and tables exist for this object to operate correctly"""
        if not schemas and not tables:
            return

        with self.get_connection() as conn:
            with conn.cursor() as cur:
                # Create schemas if they don't exist
                for schema in schemas:
                    cur.execute(sql.SQL("""
                        CREATE SCHEMA IF NOT EXISTS {}
                    """).format(sql.Identifier(schema)))
                
                # Create tables if they don't exist
                for table_name, columns in tables.items():
                    # Build column definitions
                    column_defs = []
                    for col_name, col_type in columns.items():
                        column_defs.append(f"{col_name} {col_type}")
                    
                    # Create table if it doesn't exist
                    cur.execute(sql.SQL("""
                        CREATE TABLE IF NOT EXISTS {}.{} (
                            {}
                        )
                    """).format(
                        sql.Identifier(schemas[0]),  # Use first schema
                        sql.Identifier(table_name),
                        sql.SQL(', '.join(column_defs))
                    ))
                
                conn.commit()

    @contextmanager
    def get_connection(self):
        """Context manager for database connection."""
        conn = None
        try:
            print(f"Connecting to database: {self.db_url[:20]}...")  # Only show part of URL for security
            if self.db_url.startswith('postgres://') or self.db_url.startswith('postgresql://'):
                conn = psycopg2.connect(self.db_url)
            else:
                conn = psycopg2.connect(self.db_url)
            print("Database connection successful")
            yield conn
        except Exception as e:
            print(f"Database connection error: {e}")
            if conn:
                conn.rollback()
            raise e
        finally:
            if conn:
                print("Closing database connection")
                conn.close()

    @contextmanager
    def get_cursor(self):
        """Context manager for database cursor."""
        with self.get_connection() as conn:
            cur = conn.cursor()
            try:
                yield cur
                conn.commit()
                print("Database transaction committed")
            except Exception as e:
                print(f"Database transaction error: {e}")
                conn.rollback()
                raise e
            finally:
                cur.close()
                print("Database cursor closed")

    def test_connection(self) -> bool:
        """Test the database connection."""
        try:
            with self.get_cursor() as cur:
                cur.execute("SELECT 1;")
                cur.fetchone()
            return True
        except OperationalError:
            return False
        except Exception:
            return False

    def execute_query(self, query: str, params: Optional[tuple] = None) -> list:
        """Execute a raw SQL query and return all results."""
        try:
            with self.get_cursor() as cur:
                cur.execute(query, params or ())
                if cur.description:
                    return cur.fetchall()
                return []
        except Exception as e:
            raise Exception(f"Error executing query: {str(e)}")

    def close(self):
        """No-op for compatibility; connections are closed after each use."""
        pass


class RiotPostgresManager(PostgresManager):
    def __init__(self):
        
        required_schemas = ['riot']
        required_tables = {
            'matches': {
                'match_id': 'varchar PRIMARY KEY',      # the id of the match
                'match_data': 'jsonb',                  # the jsonb data from riot api
                'created_at': 'timestamp DEFAULT NOW()' # when the match data was stored
            },
            'summoners': {
                'discord_name': 'varchar',
                'summoner_name': 'varchar',
                'summoner_tag': 'varchar',
                'puuid': 'varchar PRIMARY KEY',
                'last_updated': 'timestamp DEFAULT NOW()'
            },
            'match_messages': {
                'message_id': 'varchar PRIMARY KEY',    # the discord message id
                'match_id': 'varchar',                  # the match id
                'requesting_user_id': 'varchar',        # the id of the discord user that requested the match data
                'requesting_user': 'varchar',           # the name of the user requesting this data
                'guild': 'varchar',                     # the id of the discord server this match data was requested from
                'created_at': 'timestamp DEFAULT NOW()' # when the message was created
            }
        }
        
        required_functions = {
            'store_match': """
                CREATE OR REPLACE FUNCTION riot.store_match(
                    p_match_id varchar,
                    p_match_data jsonb
                ) RETURNS void AS $$
                BEGIN
                    INSERT INTO riot.matches (
                        match_id,
                        match_data
                    ) VALUES (
                        p_match_id,
                        p_match_data::jsonb
                    )
                    ON CONFLICT (match_id) DO UPDATE
                    SET match_data = EXCLUDED.match_data::jsonb,
                        created_at = NOW();
                END;
                $$ LANGUAGE plpgsql;
            """,
            'store_summoner': """
                CREATE OR REPLACE FUNCTION riot.store_summoner(
                    p_discord_name varchar,
                    p_summoner_name varchar,
                    p_summoner_tag varchar,
                    p_puuid varchar
                ) RETURNS void AS $$
                BEGIN
                    INSERT INTO riot.summoners (
                        discord_name,
                        summoner_name,
                        summoner_tag,
                        puuid
                    ) VALUES (
                        p_discord_name,
                        p_summoner_name,
                        p_summoner_tag,
                        p_puuid
                    )
                    ON CONFLICT (puuid) DO UPDATE
                    SET discord_name = EXCLUDED.discord_name,
                        summoner_name = EXCLUDED.summoner_name,
                        summoner_tag = EXCLUDED.summoner_tag,
                        last_updated = NOW();
                END;
                $$ LANGUAGE plpgsql;
            """,
            'store_match_message': """
                CREATE OR REPLACE FUNCTION riot.store_match_message(
                    p_message_id varchar,
                    p_match_id varchar,
                    p_requesting_user_id varchar,
                    p_requesting_user varchar,
                    p_guild varchar
                ) RETURNS void AS $$
                BEGIN
                    INSERT INTO riot.match_messages (
                        message_id,
                        match_id,
                        requesting_user_id,
                        requesting_user,
                        guild
                    ) VALUES (
                        p_message_id,
                        p_match_id,
                        p_requesting_user_id,
                        p_requesting_user,
                        p_guild
                    )
                    ON CONFLICT (message_id) DO UPDATE
                    SET match_id = EXCLUDED.match_id,
                        requesting_user_id = EXCLUDED.requesting_user_id,
                        requesting_user = EXCLUDED.requesting_user,
                        guild = EXCLUDED.guild,
                        created_at = NOW();
                END;
                $$ LANGUAGE plpgsql;
            """
        }

        super().__init__(
            required_schemas=required_schemas,
            required_tables=required_tables,
            required_functions=required_functions
        )

    def store_match(self, match_id: str, match_data: dict) -> None:
        """Store match data in the database."""
        with self.get_cursor() as cur:
            try:
                # First try to store with the function
                cur.execute("""
                    SELECT store_match(%s, %s::jsonb)
                """, (match_id, json.dumps(match_data)))
            except Exception as e:
                print(f"Error using store_match function: {e}")
                # Fallback to direct insert if function fails
                cur.execute("""
                    INSERT INTO riot.matches (match_id, match_data)
                    VALUES (%s, %s::jsonb)
                    ON CONFLICT (match_id) DO UPDATE
                    SET match_data = EXCLUDED.match_data::jsonb,
                        created_at = NOW()
                """, (match_id, json.dumps(match_data)))

    def store_summoner(self, discord_name: str, summoner_name: str, 
                      summoner_tag: str, puuid: str) -> None:
        """Store summoner data in the database."""
        with self.get_cursor() as cur:
            cur.execute("""
                SELECT store_summoner(%s, %s, %s, %s)
            """, (discord_name, summoner_name, summoner_tag, puuid))

    def store_match_message(self, message_id: str, match_id: str, 
                          requesting_user_id: str, requesting_user: str, guild: str) -> None:
        """Store the association between a Discord message and a match."""
        with self.get_cursor() as cur:
            cur.execute("""
                SELECT store_match_message(%s, %s, %s, %s, %s)
            """, (message_id, match_id, requesting_user_id, requesting_user, guild))

    def get_match_message(self, message_id: str) -> Optional[dict]:
        """Get the match message data including user and guild information."""
        with self.get_cursor() as cur:
            cur.execute("""
                SELECT match_id, requesting_user_id, requesting_user, guild, created_at 
                FROM match_messages WHERE message_id = %s
            """, (message_id,))
            result = cur.fetchone()
            if result:
                return {
                    'match_id': result[0],
                    'requesting_user_id': result[1],
                    'requesting_user': result[2],
                    'guild': result[3],
                    'created_at': result[4]
                }
            return None

    def get_match(self, match_id: str) -> Optional[dict]:
        """Retrieve match data from the database."""
        with self.get_cursor() as cur:
            cur.execute("""
                SELECT match_data FROM riot.matches WHERE match_id = %s
            """, (match_id,))
            result = cur.fetchone()
            return result[0] if result else None

    def get_summoner(self, puuid: str) -> Optional[dict]:
        """Retrieve summoner data from the database."""
        with self.get_cursor() as cur:
            cur.execute("""
                SELECT discord_name, summoner_name, summoner_tag, puuid 
                FROM riot.summoners WHERE puuid = %s
            """, (puuid,))
            result = cur.fetchone()
            if result:
                return {
                    'discord_name': result[0],
                    'summoner_name': result[1],
                    'summoner_tag': result[2],
                    'puuid': result[3]
                }
            return None



if __name__ == '__main__':
    from riot import SummonerProfile
    import asyncio

    async def fun():
        summoner = SummonerProfile('rookwood')
        await summoner.initialize()



    asyncio.run(fun())




