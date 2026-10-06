"""User-owned Sign in with ChatGPT session for the Windows desktop app.

This is an OAuth public client.  It never reads Codex Desktop's credentials,
ships an API key, or puts OAuth tokens in the app's source/data files.
The direct ChatGPT-plan flow is documented at
https://developers.openai.com/siwc/token-sharing-open-source/sign-in.
"""

from __future__ import annotations

import base64
from contextlib import contextmanager
import ctypes
from ctypes import wintypes
from hashlib import sha256
import hmac
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import secrets
import sys
import tempfile
import threading
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, urlopen
from uuid import uuid4
import webbrowser

import jwt


ISSUER = "https://auth.openai.com"
DISCOVERY_URL = ISSUER + "/.well-known/openid-configuration"
RESOURCE = "https://api.openai.com/v1"
SCOPES = "openid profile email offline_access resource.invoke chatgpt.tokens.use.direct"
CALLBACK_PATH = "/auth/callback"
AGENT_NAME = "Little Atlas"
MAX_JSON_BYTES = 256_000
AUTH_TIMEOUT_SECONDS = 300


class SIWCError(RuntimeError):
    """A safe-to-display OAuth or session error (never includes credentials)."""


class _FileTime(ctypes.Structure):
    _fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]


class _Credential(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD), ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR), ("Comment", wintypes.LPWSTR),
        ("LastWritten", _FileTime), ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
        ("Persist", wintypes.DWORD), ("AttributeCount", wintypes.DWORD),
        ("Attributes", ctypes.c_void_p), ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


class _WindowsCredentials:
    """Windows Credential Manager generic credentials, scoped to this user."""

    def __init__(self) -> None:
        if sys.platform != "win32":
            raise SIWCError("ChatGPT account storage requires Windows Credential Manager.")
        self._api = ctypes.WinDLL("advapi32", use_last_error=True)
        pointer = ctypes.POINTER(_Credential)
        self._api.CredWriteW.argtypes = (pointer, wintypes.DWORD)
        self._api.CredWriteW.restype = wintypes.BOOL
        self._api.CredReadW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                        ctypes.POINTER(pointer))
        self._api.CredReadW.restype = wintypes.BOOL
        self._api.CredDeleteW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD)
        self._api.CredDeleteW.restype = wintypes.BOOL
        self._api.CredFree.argtypes = (ctypes.c_void_p,)
        self._api.CredFree.restype = None

    @staticmethod
    def _target(registration_id: str, suffix: str = "manifest") -> str:
        return "LittleAtlas/SIWC/" + registration_id + "/" + suffix

    def _write_blob(self, registration_id: str, suffix: str, payload: bytes) -> None:
        # CRED_MAX_CREDENTIAL_BLOB_SIZE is 2560. Keep each opaque chunk smaller.
        if not payload or len(payload) > 2200:
            raise SIWCError("The ChatGPT session could not fit in secure storage.")
        buffer = (ctypes.c_ubyte * len(payload)).from_buffer_copy(payload)
        credential = _Credential()
        credential.Type = 1  # CRED_TYPE_GENERIC
        credential.TargetName = self._target(registration_id, suffix)
        credential.UserName = registration_id
        credential.CredentialBlobSize = len(payload)
        credential.CredentialBlob = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))
        credential.Persist = 2  # CRED_PERSIST_LOCAL_MACHINE, user-scoped
        if not self._api.CredWriteW(ctypes.byref(credential), 0):
            raise SIWCError("Could not save the ChatGPT session securely.")

    def _read_blob(self, registration_id: str, suffix: str) -> bytes | None:
        pointer = ctypes.POINTER(_Credential)()
        if not self._api.CredReadW(self._target(registration_id, suffix), 1, 0,
                                   ctypes.byref(pointer)):
            if ctypes.get_last_error() == 1168:  # ERROR_NOT_FOUND
                return None
            raise SIWCError("Could not read the saved ChatGPT session.")
        try:
            item = pointer.contents
            return ctypes.string_at(item.CredentialBlob, item.CredentialBlobSize)
        finally:
            self._api.CredFree(pointer)

    def _delete_blob(self, registration_id: str, suffix: str) -> None:
        if not self._api.CredDeleteW(self._target(registration_id, suffix), 1, 0):
            if ctypes.get_last_error() != 1168:
                raise SIWCError("Could not remove the saved ChatGPT session.")

    def _manifest(self, registration_id: str) -> dict[str, Any] | None:
        raw = self._read_blob(registration_id, "manifest")
        if raw is None:
            return None
        try:
            value = json.loads(raw.decode("ascii"))
            if (not isinstance(value, dict) or not isinstance(value.get("version"), str)
                    or not isinstance(value.get("count"), int)
                    or not 1 <= value["count"] <= 20):
                raise ValueError("invalid manifest")
            return value
        except (ValueError, UnicodeError, json.JSONDecodeError) as exc:
            raise SIWCError("The saved ChatGPT session is unreadable; sign in again.") from exc

    def write(self, registration_id: str, value: dict[str, Any]) -> None:
        payload = json.dumps(value, ensure_ascii=False).encode("utf-8")
        chunks = [payload[index:index + 2200] for index in range(0, len(payload), 2200)]
        if not chunks or len(chunks) > 20:
            raise SIWCError("The ChatGPT session could not fit in secure storage.")
        previous = self._manifest(registration_id)
        version = secrets.token_hex(8)
        written: list[str] = []
        try:
            for index, chunk in enumerate(chunks):
                suffix = f"{version}/{index}"
                self._write_blob(registration_id, suffix, chunk)
                written.append(suffix)
            self._write_blob(registration_id, "manifest", json.dumps({
                "version": version, "count": len(chunks),
            }).encode("ascii"))
        except SIWCError:
            for suffix in written:
                self._delete_blob(registration_id, suffix)
            raise
        if previous:
            for index in range(previous["count"]):
                self._delete_blob(registration_id, f"{previous['version']}/{index}")

    def read(self, registration_id: str) -> dict[str, Any] | None:
        manifest = self._manifest(registration_id)
        if manifest is None:
            return None
        chunks = [self._read_blob(registration_id, f"{manifest['version']}/{index}")
                  for index in range(manifest["count"])]
        if any(chunk is None for chunk in chunks):
            raise SIWCError("The saved ChatGPT session is incomplete; sign in again.")
        try:
            value = json.loads(b"".join(chunks).decode("utf-8"))
            if not isinstance(value, dict):
                raise ValueError("invalid credential")
            return value
        except (ValueError, UnicodeError, json.JSONDecodeError) as exc:
            raise SIWCError("The saved ChatGPT session is unreadable; sign in again.") from exc

    def delete(self, registration_id: str) -> None:
        manifest = self._manifest(registration_id)
        if manifest:
            self._delete_blob(registration_id, "manifest")
            for index in range(manifest["count"]):
                self._delete_blob(registration_id, f"{manifest['version']}/{index}")


def _json_request(url: str, *, method: str = "GET", body: bytes | None = None,
                  headers: dict[str, str] | None = None, limit: int = MAX_JSON_BYTES,
                  timeout: int = 15) -> dict[str, Any]:
    request = Request(url, data=body, method=method,
                      headers={"Accept": "application/json", **(headers or {})})
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read(limit + 1)
    except HTTPError as exc:
        if exc.code in (400, 401, 403):
            raise SIWCError("ChatGPT authorization was declined or expired; sign in again.") from exc
        raise SIWCError(f"ChatGPT service returned HTTP {exc.code}.") from exc
    except (URLError, OSError, TimeoutError) as exc:
        raise SIWCError("Could not reach ChatGPT. Check your connection.") from exc
    if len(raw) > limit:
        raise SIWCError("ChatGPT returned an unexpectedly large response.")
    try:
        value = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise SIWCError("ChatGPT returned an unreadable response.") from exc
    if not isinstance(value, dict):
        raise SIWCError("ChatGPT returned an unexpected response.")
    return value


def _post_form(url: str, fields: dict[str, str], *, empty_ok: bool = False) -> dict[str, Any]:
    body = urlencode(fields).encode("ascii")
    if empty_ok:
        request = Request(url, data=body, method="POST",
                          headers={"Content-Type": "application/x-www-form-urlencoded"})
        try:
            with urlopen(request, timeout=15) as response:
                response.read(1)
        except (HTTPError, URLError, OSError, TimeoutError) as exc:
            raise SIWCError("Remote ChatGPT sign-out could not be confirmed.") from exc
        return {}
    return _json_request(url, method="POST", body=body,
                         headers={"Content-Type": "application/x-www-form-urlencoded"})


def _safe_endpoint(value: object) -> str:
    if not isinstance(value, str) or not value.startswith(ISSUER + "/"):
        raise SIWCError("ChatGPT identity configuration was unexpected.")
    return value


def _registration_key(client_id: str, subject: str) -> str:
    return sha256((client_id + "\0" + subject).encode("utf-8")).hexdigest()[:32]


@contextmanager
def _refresh_guard(data_dir: Path):
    """Serialize rotating refresh tokens across simultaneous app processes."""
    if sys.platform != "win32":
        yield
        return
    import msvcrt

    with (data_dir / "chatgpt_refresh.lock").open("a+b") as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        deadline = time.monotonic() + 20
        while True:
            try:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except OSError as exc:
                if time.monotonic() >= deadline:
                    raise SIWCError("Another Little Atlas window is renewing ChatGPT; try again.") from exc
                time.sleep(0.1)
        try:
            yield
        finally:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


class SIWCClient:
    """Owns one installation's OAuth registrations and active user session.

    ``sign_in`` blocks during browser authorization and must be called from a
    worker, never the Qt UI thread. Tokens are saved only in Credential Manager.
    """

    def __init__(self, data_dir: str | Path, *, credential_store: Any | None = None) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._path = self.data_dir / "chatgpt_accounts.json"
        self._credentials = credential_store if credential_store is not None else _WindowsCredentials()
        self._lock = threading.RLock()
        self._discovery_cache: dict[str, Any] | None = None
        self._state = self._load_state()

    def _load_state(self) -> dict[str, Any]:
        try:
            value = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            value = {"host_id": "urn:uuid:" + str(uuid4()), "registrations": {}, "active": None}
            self._save_state(value)
        except (OSError, ValueError) as exc:
            raise SIWCError("ChatGPT account settings are unreadable.") from exc
        if (not isinstance(value, dict) or not isinstance(value.get("host_id"), str)
                or not value["host_id"].startswith("urn:uuid:")
                or not isinstance(value.get("registrations"), dict)):
            raise SIWCError("ChatGPT account settings are invalid.")
        return value

    def _save_state(self, value: dict[str, Any]) -> None:
        name = ""
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=self.data_dir,
                                             prefix=".chatgpt-", suffix=".tmp",
                                             delete=False) as handle:
                name = handle.name
                json.dump(value, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(name, self._path)
        finally:
            if name:
                try:
                    os.unlink(name)
                except FileNotFoundError:
                    pass

    def _discovery(self) -> dict[str, Any]:
        if self._discovery_cache is None:
            value = _json_request(DISCOVERY_URL)
            if value.get("issuer") != ISSUER:
                raise SIWCError("ChatGPT identity issuer was unexpected.")
            for name in ("authorization_endpoint", "token_endpoint", "jwks_uri",
                         "revocation_endpoint"):
                _safe_endpoint(value.get(name))
            self._discovery_cache = value
        return self._discovery_cache

    def _verify_id_token(self, encoded: str, client_id: str, nonce: str) -> dict[str, Any]:
        try:
            header = jwt.get_unverified_header(encoded)
            if header.get("alg") != "RS256" or not isinstance(header.get("kid"), str):
                raise SIWCError("ChatGPT identity token used an unexpected signature.")
            jwks = _json_request(self._discovery()["jwks_uri"])
            public_jwk = next((key for key in jwks.get("keys", [])
                               if isinstance(key, dict) and key.get("kid") == header["kid"]
                               and key.get("kty") == "RSA"), None)
            if public_jwk is None:
                raise SIWCError("ChatGPT identity signing key was unavailable.")
            key = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(public_jwk))
            claims = jwt.decode(encoded, key=key, algorithms=["RS256"],
                                audience=client_id, issuer=ISSUER, leeway=30,
                                options={"require": ["exp", "iat", "iss", "aud", "sub"]})
            if not hmac.compare_digest(str(claims.get("nonce", "")), nonce):
                raise SIWCError("ChatGPT identity nonce did not match.")
            if not isinstance(claims.get("sub"), str) or not claims["sub"]:
                raise SIWCError("ChatGPT identity had no account identifier.")
            return claims
        except jwt.PyJWTError as exc:
            raise SIWCError("ChatGPT identity token could not be verified.") from exc
        except (ValueError, TypeError, KeyError) as exc:
            raise SIWCError("ChatGPT identity token was invalid.") from exc

    def _preferred_registration(self, requested: str | None = None) -> tuple[str | None, dict[str, Any] | None]:
        records = self._state["registrations"]
        chosen = requested or self._state.get("active")
        if chosen is None and len(records) == 1:
            chosen = next(iter(records))
        if chosen is None:
            return None, None
        record = records.get(chosen)
        if not isinstance(record, dict):
            raise SIWCError("The selected ChatGPT account was not found.")
        return chosen, record

    def sign_in(self, *, registration_id: str | None = None,
                new_account: bool = False) -> dict[str, str]:
        """Run the system-browser OAuth PKCE flow and activate a verified account."""
        with self._lock:
            chosen, record = (None, None) if new_account else self._preferred_registration(registration_id)
            discovery = self._discovery()
            verifier = secrets.token_urlsafe(48)
            challenge = base64.urlsafe_b64encode(sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
            state = secrets.token_urlsafe(32)
            nonce = secrets.token_urlsafe(32)
            callback: dict[str, str] = {}

            class CallbackHandler(BaseHTTPRequestHandler):
                def do_GET(self) -> None:  # noqa: N802 - stdlib HTTP handler contract
                    parsed = urlsplit(self.path)
                    query = parse_qs(parsed.query, keep_blank_values=True)
                    supplied = query.get("state", [""])[0]
                    if parsed.path != CALLBACK_PATH or not hmac.compare_digest(supplied, state):
                        self.send_error(400)
                        return
                    for key, values in query.items():
                        if values:
                            callback[key] = values[0]
                    message = "You may close this tab and return to Little Atlas."
                    body = ("<!doctype html><meta charset='utf-8'><title>Little Atlas</title>"
                            "<p style='font:16px sans-serif;margin:3rem'>" + message + "</p>").encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)

                def log_message(self, _format: str, *_args: object) -> None:
                    pass  # Authorization codes never enter logs.

            with HTTPServer(("127.0.0.1", 0), CallbackHandler) as server:
                server.timeout = 1
                redirect_uri = f"http://127.0.0.1:{server.server_port}{CALLBACK_PATH}"
                client_id = str(record["client_id"]) if record else "dynamic_agent_client"
                params = {
                    "client_id": client_id,
                    "ext_agent_host_id": self._state["host_id"],
                    "response_type": "code", "redirect_uri": redirect_uri,
                    "scope": SCOPES, "resource": RESOURCE, "state": state,
                    "nonce": nonce, "code_challenge_method": "S256",
                    "code_challenge": challenge,
                }
                if record:
                    saved = self._credentials.read(chosen)
                    if saved and isinstance(saved.get("id_token"), str):
                        params["id_token_hint"] = saved["id_token"]
                    if record.get("email"):
                        params["login_hint"] = str(record["email"])
                else:
                    params["agent_name_hint"] = AGENT_NAME
                auth_url = discovery["authorization_endpoint"] + "?" + urlencode(params)
                if not webbrowser.open(auth_url):
                    raise SIWCError("Could not open your browser for ChatGPT sign-in.")
                deadline = time.monotonic() + AUTH_TIMEOUT_SECONDS
                while not callback and time.monotonic() < deadline:
                    server.handle_request()
            if not callback:
                raise SIWCError("ChatGPT sign-in timed out; please try again.")
            if callback.get("error"):
                raise SIWCError("ChatGPT sign-in was cancelled or denied.")
            code = callback.get("code", "")
            if not code:
                raise SIWCError("ChatGPT did not return an authorization code.")
            issued_id = callback.get("client_id", "")
            if record:
                if issued_id and issued_id != client_id:
                    raise SIWCError("ChatGPT returned a different registered client.")
                issued_id = client_id
            elif not issued_id or issued_id == "dynamic_agent_client":
                raise SIWCError("ChatGPT registration did not return a client ID.")
            token = _post_form(discovery["token_endpoint"], {
                "grant_type": "authorization_code", "client_id": issued_id,
                "code": code, "code_verifier": verifier,
                "redirect_uri": redirect_uri, "resource": RESOURCE,
            })
            scope = str(token.get("scope", "")).split()
            if "chatgpt.tokens.use.direct" not in scope:
                raise SIWCError("This ChatGPT account did not grant plan usage.")
            if token.get("token_type", "").lower() != "bearer":
                raise SIWCError("ChatGPT returned an unexpected token type.")
            if not all(isinstance(token.get(key), str) and token[key]
                       for key in ("id_token", "access_token", "refresh_token")):
                raise SIWCError("ChatGPT did not return a renewable session.")
            claims = self._verify_id_token(token["id_token"], issued_id, nonce)
            subject = claims["sub"]
            if record and subject != record["subject"]:
                raise SIWCError("A different ChatGPT account was selected.")
            key = _registration_key(issued_id, subject)
            try:
                expires_in = int(token.get("expires_in", 0))
            except (TypeError, ValueError) as exc:
                raise SIWCError("ChatGPT returned an invalid session expiry.") from exc
            if expires_in <= 0:
                raise SIWCError("ChatGPT returned an invalid session expiry.")
            session = {
                "access_token": token["access_token"],
                "refresh_token": token["refresh_token"],
                "id_token": token["id_token"],
                "scope": scope,
                "expires_at": time.time() + expires_in,
            }
            self._credentials.write(key, session)
            email = str(claims.get("email", ""))
            self._state["registrations"][key] = {
                "client_id": issued_id, "subject": subject, "email": email,
            }
            self._state["active"] = key
            self._save_state(self._state)
            return {"email": email, "subject": subject, "client_id": issued_id,
                    "registration_id": key}

    def profile(self) -> dict[str, str] | None:
        with self._lock:
            key, record = self._preferred_registration()
            if not key or not record or self._state.get("active") != key:
                return None
            session = self._credentials.read(key)
            if (not session or not session.get("refresh_token")
                    or "chatgpt.tokens.use.direct" not in session.get("scope", [])):
                return None
            return {"email": str(record.get("email", "")),
                    "subject": str(record["subject"]),
                    "client_id": str(record["client_id"]),
                    "registration_id": key}

    def is_signed_in(self) -> bool:
        return self.profile() is not None

    def access_token(self) -> str:
        """Return a fresh bearer token; refresh on demand under a local lock."""
        with self._lock:
            key, record = self._preferred_registration()
            if not key or not record or self._state.get("active") != key:
                raise SIWCError("Sign in with ChatGPT first.")
            with _refresh_guard(self.data_dir):
                # Read after acquiring the cross-process lock: another window
                # may already have rotated the refresh token.
                session = self._credentials.read(key)
                if not session or not session.get("refresh_token"):
                    raise SIWCError("The ChatGPT session is missing; sign in again.")
                try:
                    expires_at = float(session.get("expires_at", 0))
                except (ValueError, TypeError) as exc:
                    raise SIWCError("The saved ChatGPT session is unreadable; sign in again.") from exc
                if session.get("access_token") and expires_at > time.time() + 90:
                    return str(session["access_token"])
                token = _post_form(self._discovery()["token_endpoint"], {
                    "grant_type": "refresh_token", "client_id": str(record["client_id"]),
                    "refresh_token": str(session["refresh_token"]), "resource": RESOURCE,
                })
                if token.get("token_type", "Bearer").lower() != "bearer":
                    raise SIWCError("ChatGPT returned an unexpected token type.")
                if not isinstance(token.get("access_token"), str) or not token["access_token"]:
                    raise SIWCError("ChatGPT could not renew the session; sign in again.")
                scopes = str(token.get("scope", "")).split() if token.get("scope") else session.get("scope", [])
                if "chatgpt.tokens.use.direct" not in scopes:
                    raise SIWCError("This ChatGPT account no longer grants plan usage.")
                try:
                    expires_in = int(token.get("expires_in", 0))
                except (ValueError, TypeError) as exc:
                    raise SIWCError("ChatGPT returned an invalid session expiry.") from exc
                if expires_in <= 0:
                    raise SIWCError("ChatGPT returned an invalid session expiry.")
                updated = {**session, "access_token": token["access_token"],
                           "refresh_token": token.get("refresh_token") or session["refresh_token"],
                           "scope": scopes, "expires_at": time.time() + expires_in}
                self._credentials.write(key, updated)
                return str(updated["access_token"])

    def sign_out(self) -> None:
        """Revoke the active renewable session, then clear local credentials."""
        with self._lock:
            key, record = self._preferred_registration()
            if not key or not record:
                return
            session = self._credentials.read(key)
            error: SIWCError | None = None
            if session and session.get("refresh_token"):
                try:
                    _post_form(self._discovery()["revocation_endpoint"], {
                        "token": str(session["refresh_token"]),
                        "token_type_hint": "refresh_token",
                        "client_id": str(record["client_id"]),
                    }, empty_ok=True)
                except SIWCError as exc:
                    error = exc
            self._credentials.delete(key)
            self._state["active"] = None
            self._save_state(self._state)
            if error:
                raise SIWCError("Signed out locally, but remote revocation was not confirmed. "+
                                "You can disconnect Little Atlas in ChatGPT Settings.") from error
