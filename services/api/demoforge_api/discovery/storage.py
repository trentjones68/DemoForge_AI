"""Server-only transport restricted to discovery objects in trusted Supabase Storage."""

from urllib.parse import parse_qs, urlencode, urlsplit
from uuid import UUID

import httpx2
from fastapi import HTTPException

from demoforge_api.discovery.parser import FORMAT_MIME
from demoforge_api.settings import Settings

BUCKET = "discovery-originals"
SIGNED_SECONDS = 60


def object_key(workspace: UUID, session: UUID, source: UUID, fmt: str) -> str:
    return f"{workspace}/{session}/{source}.{fmt}"


class DiscoveryStorage:
    def __init__(self, settings: Settings) -> None:
        self.base = (
            str(settings.supabase_storage_url).rstrip("/") if settings.supabase_storage_url else ""
        )
        self.key = settings.supabase_storage_service_key

    def require_configured(self) -> None:
        if not self.base or self.key is None:
            raise HTTPException(503, "Discovery storage is unavailable.")

    def save(self, key: str, fmt: str, content: bytes) -> None:
        with self.client() as client:
            # A retry uses the original reservation and can only write the same SHA-256 bytes.
            try:
                response = client.post(
                    f"object/{BUCKET}/{key}",
                    content=content,
                    headers={"Content-Type": FORMAT_MIME[fmt], "x-upsert": "true"},
                )
            except httpx2.RequestError:
                raise HTTPException(
                    503, "Storage is unavailable. Retry with the same source."
                ) from None
        if not response.is_success:
            raise HTTPException(503, "Storage is unavailable. Retry with the same source.")

    def sign(self, key: str, fmt: str) -> str:
        path = f"/object/sign/{BUCKET}/{key}"
        try:
            with self.client() as client:
                response = client.post(path.lstrip("/"), json={"expiresIn": SIGNED_SECONDS})
            response.raise_for_status()
            signed = urlsplit(response.json()["signedURL"])
            tokens = parse_qs(signed.query).get("token", [])
            if (
                signed.netloc
                or signed.scheme
                or signed.fragment
                or signed.path not in (path, urlsplit(self.base).path + path)
                or len(tokens) != 1
                or not tokens[0]
            ):
                raise ValueError("Invalid Storage response")
        except (httpx2.HTTPError, KeyError, ValueError, TypeError, AttributeError):
            raise HTTPException(503, "Original download is unavailable.") from None
        query = urlencode({"token": tokens[0], "download": f"original.{fmt}"})
        return f"{self.base}{path}?{query}"

    def client(self) -> httpx2.Client:
        self.require_configured()
        assert self.key is not None
        key = self.key.get_secret_value()
        headers = {"apikey": key}
        # Legacy service-role JWT used by CLI projects. Hosted secret keys use apikey only.
        if not key.startswith("sb_secret_"):
            headers["Authorization"] = f"Bearer {key}"
        return httpx2.Client(
            base_url=f"{self.base}/", headers=headers, timeout=5.0, trust_env=False
        )
