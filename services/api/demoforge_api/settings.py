from typing import Self

from pydantic import HttpUrl, PostgresDsn, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    database_url: PostgresDsn | None = None
    migration_database_url: PostgresDsn | None = None
    supabase_jwt_issuer: HttpUrl | None = None
    supabase_jwks_url: HttpUrl | None = None
    supabase_jwt_audience: str = "authenticated"
    supabase_jwt_secret: SecretStr | None = None
    supabase_storage_url: HttpUrl | None = None
    supabase_storage_service_key: SecretStr | None = None

    @model_validator(mode="after")
    def check_signing_configuration(self) -> Self:
        if self.supabase_jwks_url is not None and self.supabase_jwt_secret is not None:
            raise ValueError("Configure either JWKS or the legacy JWT secret")
        if (
            self.supabase_jwt_secret is not None
            and len(self.supabase_jwt_secret.get_secret_value()) < 32
        ):
            raise ValueError("The legacy JWT secret must be at least 32 characters")
        if self.supabase_jwt_issuer is None and (
            self.supabase_jwks_url is not None or self.supabase_jwt_secret is not None
        ):
            raise ValueError("Configure SUPABASE_JWT_ISSUER for token verification")
        storage = self.supabase_storage_url
        if (storage is None) != (self.supabase_storage_service_key is None):
            raise ValueError("Configure both the Storage URL and server-side key")
        if storage is not None and (
            storage.username is not None
            or storage.password is not None
            or storage.query is not None
            or storage.fragment is not None
            or (storage.scheme != "https" and storage.host not in ("localhost", "127.0.0.1"))
        ):
            raise ValueError("Use a trusted HTTPS Storage URL or a local development endpoint")
        return self
