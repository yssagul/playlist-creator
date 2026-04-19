#!/usr/bin/env python3
"""
Interactive Tidal API scratch pad.
Usage: python test_tidal.py
"""

import json
import ssl
import urllib.error
import urllib.parse
import urllib.request
import uuid

import certifi

from tidal_auth import TidalAuth

API_BASE = "https://openapi.tidal.com/v2"
_SSL = ssl.create_default_context(cafile=certifi.where())


def get(auth: TidalAuth, path: str, params: dict = None) -> dict:
    url = f"{API_BASE}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params, doseq=True)
    print(f"\nGET {url}")
    req = urllib.request.Request(url, headers=auth.headers())
    try:
        with urllib.request.urlopen(req, context=_SSL) as resp:
            data = json.loads(resp.read())
            print(json.dumps(data, indent=2)[:3000])
            return data
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode()[:1000]}")
        return {}


def post(auth: TidalAuth, path: str, body: dict, params: dict = None) -> dict:
    url = f"{API_BASE}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    print(f"\nPOST {url}")
    data = json.dumps(body).encode()
    headers = auth.headers()
    headers["Idempotency-Key"] = str(uuid.uuid4())
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, context=_SSL) as resp:
            result = json.loads(resp.read())
            print(json.dumps(result, indent=2)[:3000])
            return result
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode()[:1000]}")
        return {}


if __name__ == "__main__":
    auth = TidalAuth()
    print("Auth OK.")

    # Edit below to explore the API
    get(auth, "/playlists/e3380f7f-c425-45fc-8598-bb28ad9de771", {"countryCode": "US"})
