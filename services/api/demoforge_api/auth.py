from uuid import UUID

import jwt
from fastapi import HTTPException
from jwt import PyJWK, PyJWKClient
from jwt.exceptions import InvalidTokenError, PyJWKClientError

from demoforge_api.settings import Settings

PUBLIC_ALGORITHMS = ("ES256", "RS256")


class TokenVerifier:
    def __init__(self, settings: Settings) -> None:
        self.issuer = (
            str(settings.supabase_jwt_issuer).rstrip("/") if settings.supabase_jwt_issuer else None
        )
        self.audience = settings.supabase_jwt_audience
        self.secret = settings.supabase_jwt_secret
        self.jwks = (
            PyJWKClient(str(settings.supabase_jwks_url), lifespan=60, timeout=3)
            if settings.supabase_jwks_url
            else None
        )

    def subject(self, token: str) -> UUID:
        if self.issuer is None or (self.jwks is None and self.secret is None):
            raise HTTPException(503, "Authentication unavailable")

        try:
            if len(token) > 8192:
                raise InvalidTokenError("Oversized token")
            header = jwt.get_unverified_header(token)
            algorithm = header.get("alg")
            signing_key: PyJWK | str
            if self.jwks is not None and algorithm in PUBLIC_ALGORITHMS:
                kid = header.get("kid")
                if not isinstance(kid, str) or not 0 < len(kid) <= 128:
                    raise InvalidTokenError("Invalid key ID")
                # Cache the trusted key set. A caller-supplied unknown kid cannot trigger a fetch.
                key = next(
                    (
                        key
                        for key in self.jwks.get_signing_keys()
                        if key.key_id == kid and key.algorithm_name == algorithm
                    ),
                    None,
                )
                if key is None:
                    raise InvalidTokenError("Unknown key ID")
                signing_key = key
            elif self.secret is not None and algorithm == "HS256":
                signing_key = self.secret.get_secret_value()
            else:
                raise InvalidTokenError("Unsupported algorithm")

            claims = jwt.decode(
                token,
                signing_key,
                algorithms=[algorithm],
                issuer=self.issuer,
                audience=self.audience,
                options={"require": ["iss", "aud", "sub", "exp", "iat"]},
                leeway=5,
            )
            if (
                claims.get("role") != "authenticated"
                or claims.get("is_anonymous", False) is not False
            ):
                raise InvalidTokenError("Unsupported identity")
            subject = claims["sub"]
            if not isinstance(subject, str):
                raise InvalidTokenError("Invalid subject")
            return UUID(subject)
        except (InvalidTokenError, ValueError, TypeError):
            raise HTTPException(
                401, "Invalid access token", headers={"WWW-Authenticate": "Bearer"}
            ) from None
        except PyJWKClientError:
            raise HTTPException(503, "Authentication unavailable") from None
