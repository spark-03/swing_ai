"""
Supabase client with connection pooling, retry logic, and health checks.
"""
import os
import time
import logging
from typing import Optional, Any, Dict, List
from functools import wraps
from supabase import create_client, Client
from postgrest import APIError

logger = logging.getLogger(__name__)


class SupabaseClient:
    """Wrapper around Supabase client with retry logic and connection management."""

    def __init__(
        self,
        url: Optional[str] = None,
        key: Optional[str] = None,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
    ):
        self.url = url or os.getenv("SUPABASE_URL")
        self.key = key or os.getenv("SUPABASE_KEY")
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self._client: Optional[Client] = None

    @property
    def client(self) -> Client:
        """Lazy initialization of Supabase client."""
        if self._client is None:
            if not self.url or not self.key:
                raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set")
            self._client = create_client(self.url, self.key)
        return self._client

    def _retry_with_backoff(self, func, *args, **kwargs):
        """Execute function with exponential backoff retry logic."""
        last_exception = None
        delay = self.base_delay

        for attempt in range(self.max_retries + 1):
            try:
                return func(*args, **kwargs)
            except APIError as e:
                last_exception = e
                if attempt < self.max_retries:
                    logger.warning(
                        f"Supabase API error (attempt {attempt + 1}/{self.max_retries + 1}): {e}. "
                        f"Retrying in {delay:.1f}s..."
                    )
                    time.sleep(delay)
                    delay = min(delay * 2, self.max_delay)
                else:
                    logger.error(f"Supabase API error after {self.max_retries + 1} attempts: {e}")
                    raise
            except Exception as e:
                last_exception = e
                if attempt < self.max_retries:
                    logger.warning(
                        f"Unexpected error (attempt {attempt + 1}/{self.max_retries + 1}): {e}. "
                        f"Retrying in {delay:.1f}s..."
                    )
                    time.sleep(delay)
                    delay = min(delay * 2, self.max_delay)
                else:
                    logger.error(f"Unexpected error after {self.max_retries + 1} attempts: {e}")
                    raise

        raise last_exception

    def select(
        self,
        table: str,
        columns: str = "*",
        filters: Optional[Dict[str, Any]] = None,
        order: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Select rows from a table with optional filters."""
        def _select():
            query = self.client.table(table).select(columns)
            if filters:
                for col, val in filters.items():
                    query = query.eq(col, val)
            if order:
                query = query.order(order)
            if limit:
                query = query.limit(limit)
            result = query.execute()
            return result.data or []

        return self._retry_with_backoff(_select)

    def insert(self, table: str, data: Dict[str, Any] | List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Insert row(s) into a table."""
        def _insert():
            result = self.client.table(table).insert(data).execute()
            return result.data or []

        return self._retry_with_backoff(_insert)

    def upsert(self, table: str, data: Dict[str, Any] | List[Dict[str, Any]], on_conflict: Optional[str] = None) -> List[Dict[str, Any]]:
        """Upsert row(s) into a table."""
        def _upsert():
            query = self.client.table(table).upsert(data)
            if on_conflict:
                query = query.on_conflict(on_conflict)
            result = query.execute()
            return result.data or []

        return self._retry_with_backoff(_upsert)

    def update(self, table: str, data: Dict[str, Any], filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Update rows in a table."""
        def _update():
            query = self.client.table(table).update(data)
            for col, val in filters.items():
                query = query.eq(col, val)
            result = query.execute()
            return result.data or []

        return self._retry_with_backoff(_update)

    def delete(self, table: str, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Delete rows from a table."""
        def _delete():
            query = self.client.table(table).delete()
            for col, val in filters.items():
                query = query.eq(col, val)
            result = query.execute()
            return result.data or []

        return self._retry_with_backoff(_delete)

    def rpc(self, function_name: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """Call a PostgreSQL function."""
        def _rpc():
            result = self.client.rpc(function_name, params or {}).execute()
            return result.data

        return self._retry_with_backoff(_rpc)

    def health_check(self) -> bool:
        """Check if Supabase connection is healthy."""
        try:
            self.client.table("current_portfolio").select("count", count="exact", head=True).execute()
            return True
        except Exception as e:
            logger.error(f"Supabase health check failed: {e}")
            return False


# Global instance
_supabase_client: Optional[SupabaseClient] = None


def get_supabase_client() -> SupabaseClient:
    """Get or create the global Supabase client instance."""
    global _supabase_client
    if _supabase_client is None:
        _supabase_client = SupabaseClient()
    return _supabase_client


def reset_supabase_client() -> None:
    """Reset the global Supabase client (useful for testing)."""
    global _supabase_client
    _supabase_client = None