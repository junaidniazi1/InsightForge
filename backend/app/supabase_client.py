"""Thin Supabase REST + Storage client using httpx.

We deliberately avoid the supabase-py SDK to keep deps small and async-native.
Only the endpoints we use are implemented.
"""

from typing import Any

import httpx

from .config import Settings


class SupabaseClient:
    def __init__(self, settings: Settings) -> None:
        self.url = settings.supabase_url.rstrip("/")
        self.key = settings.supabase_service_role_key
        self._client: httpx.AsyncClient | None = None

    async def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(60.0, connect=10.0),
                headers={
                    "apikey": self.key,
                    "Authorization": f"Bearer {self.key}",
                },
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # ---- REST (PostgREST) ----
    async def table_get(self, table: str, params: dict[str, str]) -> list[dict[str, Any]]:
        client = await self._http()
        r = await client.get(f"{self.url}/rest/v1/{table}", params=params)
        r.raise_for_status()
        return r.json()

    async def table_insert(
        self, table: str, row: dict[str, Any], *, returning: str = "representation"
    ) -> list[dict[str, Any]]:
        client = await self._http()
        r = await client.post(
            f"{self.url}/rest/v1/{table}",
            json=row,
            headers={"Prefer": f"return={returning}"},
        )
        r.raise_for_status()
        return r.json() if returning != "minimal" else []

    async def table_update(
        self, table: str, params: dict[str, str], patch: dict[str, Any]
    ) -> list[dict[str, Any]]:
        client = await self._http()
        r = await client.patch(
            f"{self.url}/rest/v1/{table}",
            params=params,
            json=patch,
            headers={"Prefer": "return=representation"},
        )
        r.raise_for_status()
        return r.json()

    async def table_delete(self, table: str, params: dict[str, str]) -> None:
        client = await self._http()
        r = await client.delete(f"{self.url}/rest/v1/{table}", params=params)
        r.raise_for_status()

    # ---- Storage ----
    async def storage_download(self, bucket: str, path: str) -> bytes:
        client = await self._http()
        r = await client.get(f"{self.url}/storage/v1/object/{bucket}/{path}")
        r.raise_for_status()
        return r.content

    async def storage_upload(
        self, bucket: str, path: str, data: bytes, *, content_type: str = "text/csv"
    ) -> None:
        client = await self._http()
        r = await client.post(
            f"{self.url}/storage/v1/object/{bucket}/{path}",
            content=data,
            headers={"Content-Type": content_type, "x-upsert": "true"},
        )
        r.raise_for_status()

    async def storage_delete(self, bucket: str, path: str) -> None:
        """Delete a single object. Raises on non-2xx; callers decide whether
        to treat a 404 as benign (file already gone)."""
        client = await self._http()
        r = await client.delete(f"{self.url}/storage/v1/object/{bucket}/{path}")
        r.raise_for_status()
