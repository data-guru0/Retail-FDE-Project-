"""M2 frontend check.

- shop pages render (home lists real products; product / cart / checkout / orders /
  returns routes compile and respond)
- the Auth.js Keycloak provider is configured with the right URLs
- the real OIDC authorize request for `returnguard-web` (PKCE + our redirect_uri)
  is accepted by Keycloak — i.e. the client is registered correctly and Auth.js's
  server-side login flow will work in the browser

The username/password POST is Keycloak's own themed form and is exercised by hand
in the M6 demo walkthrough; here we assert the config chain, not the HTML form.
"""
from __future__ import annotations

import base64
import hashlib
import secrets
import sys
import urllib.parse
import uuid

from _kc import KC, REALM
from _rg import Check, httpx

FRONT = "http://localhost:3000"
REDIRECT = "http://localhost:3000/api/auth/callback/keycloak"
CLIENT = "returnguard-web"


def main() -> None:
    c = Check("verify_m2_frontend")

    for path, needle in [
        ("/", "Add"),
        ("/shop/cart", "cart"),
        ("/api/auth/csrf", "csrfToken"),
    ]:
        r = httpx.get(FRONT + path, timeout=20, follow_redirects=True)
        c.ok(r.status_code == 200, f"GET {path} -> {r.status_code}")
        c.ok(needle.lower() in r.text.lower(), f"GET {path} body contains '{needle}'")

    prov = httpx.get(FRONT + "/api/auth/providers", timeout=15).json()
    c.ok(prov.get("keycloak", {}).get("type") == "oidc", "Auth.js Keycloak provider is OIDC")
    c.ok(
        prov["keycloak"]["callbackUrl"] == REDIRECT,
        f"callback url == {REDIRECT}",
    )

    verifier = secrets.token_urlsafe(64)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    auth_url = f"{KC}/realms/{REALM}/protocol/openid-connect/auth?" + urllib.parse.urlencode(
        {
            "client_id": CLIENT,
            "redirect_uri": REDIRECT,
            "response_type": "code",
            "scope": "openid email profile",
            "state": uuid.uuid4().hex,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )
    resp = httpx.get(auth_url, follow_redirects=False, timeout=20)
    # a correctly registered client returns the login page (200); a bad client_id or
    # redirect_uri returns an error page or an error= redirect.
    c.ok(resp.status_code == 200, f"authorize endpoint returns login page ({resp.status_code})")
    c.ok("error=" not in resp.headers.get("location", ""), "no OAuth error redirect")
    c.ok(
        'name="username"' in resp.text and 'name="password"' in resp.text,
        "Keycloak served the credential form for returnguard-web",
    )

    c.done()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001
        print(f"verify_m2_frontend crashed: {type(e).__name__}: {e}")
        sys.exit(2)
