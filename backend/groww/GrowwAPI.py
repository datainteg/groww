"""Standalone scratch helper to mint a Groww access token from the CLI.
NOT used by the app — the live app stores/reads the per-user token in MongoDB
(set via Profile -> update Groww credentials). Provide secrets via env, never
hardcode them:  GROWW_API_KEY=... GROWW_API_SECRET=... python GrowwAPI.py
"""
import os
from growwapi import GrowwAPI

api_key = os.getenv("GROWW_API_KEY", "")
secret = os.getenv("GROWW_API_SECRET", "")
if not api_key or not secret:
    raise SystemExit("Set GROWW_API_KEY and GROWW_API_SECRET environment variables.")

access_token = GrowwAPI.get_access_token(api_key=api_key, secret=secret)

print("Access Token:", access_token)
# Use access_token to initiate GrowwAPI
groww = GrowwAPI(access_token)