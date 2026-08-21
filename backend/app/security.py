"""
Signed table identity tokens.

The QR code on each physical table encodes one of these tokens instead of a
raw table_id. A customer cannot edit the URL to view another table's session,
because the signature is verified server-side on every order-creating request.

Format: base64url(branch_id:table_id:signature)
signature = HMAC-SHA256(secret, f"{branch_id}:{table_id}")[:16] as hex
"""
import hmac
import hashlib
import base64
import os

# In production, set ORBIT_SIGNING_SECRET as a real random secret via env var.
SECRET = os.getenv("ORBIT_SIGNING_SECRET", "dev-only-secret-change-in-production").encode()


def _sign(branch_id: str, table_id: str) -> str:
    msg = f"{branch_id}:{table_id}".encode()
    return hmac.new(SECRET, msg, hashlib.sha256).hexdigest()[:16]


def make_table_token(branch_id: str, table_id: str) -> str:
    sig = _sign(branch_id, table_id)
    raw = f"{branch_id}:{table_id}:{sig}"
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


class InvalidTableToken(Exception):
    pass


def verify_table_token(token: str) -> tuple[str, str]:
    """Returns (branch_id, table_id) or raises InvalidTableToken."""
    try:
        clean = token.strip()
        # Handle cases where '+' in base64 was decoded as space by web server or browser
        padded = clean + "=" * (-len(clean) % 4)
        try:
            raw = base64.urlsafe_b64decode(padded.encode()).decode()
        except Exception:
            padded_alt = clean.replace(" ", "+") + "=" * (-len(clean) % 4)
            raw = base64.b64decode(padded_alt.encode()).decode()
        branch_id, table_id, sig = raw.split(":")
    except Exception:
        raise InvalidTableToken("Malformed token")

    expected = _sign(branch_id, table_id)
    if not hmac.compare_digest(sig, expected):
        raise InvalidTableToken("Signature mismatch — token was tampered with")

    return branch_id, table_id



# --- Staff password hashing (PBKDF2, no extra dependency needed) ---

def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000)
    return base64.b64encode(salt).decode() + "$" + base64.b64encode(digest).decode()


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_b64, digest_b64 = stored.split("$")
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
    except Exception:
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000)
    return hmac.compare_digest(actual, expected)


# --- Staff session tokens (signed, carries role + branch, expires) ---

class InvalidStaffToken(Exception):
    pass


def make_staff_token(user_id: str, branch_id: str, role: str) -> str:
    import time
    issued_at = str(int(time.time()))
    msg = f"{user_id}:{branch_id}:{role}:{issued_at}".encode()
    sig = hmac.new(SECRET, msg, hashlib.sha256).hexdigest()[:16]
    raw = f"{user_id}:{branch_id}:{role}:{issued_at}:{sig}"
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def verify_staff_token(token: str, max_age_seconds: int = 12 * 3600) -> dict:
    import time
    try:
        padded = token + "=" * (-len(token) % 4)
        raw = base64.urlsafe_b64decode(padded.encode()).decode()
        user_id, branch_id, role, issued_at, sig = raw.split(":")
    except Exception:
        raise InvalidStaffToken("Malformed session token")

    expected = hmac.new(SECRET, f"{user_id}:{branch_id}:{role}:{issued_at}".encode(), hashlib.sha256).hexdigest()[:16]
    if not hmac.compare_digest(sig, expected):
        raise InvalidStaffToken("Signature mismatch")
    if time.time() - int(issued_at) > max_age_seconds:
        raise InvalidStaffToken("Session expired, please log in again")

    return {"user_id": user_id, "branch_id": branch_id, "role": role}
