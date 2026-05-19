"""Shared Google OAuth2 authentication module for Calendar and Gmail tools."""
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import os
import pickle


SCOPES = [
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/gmail.modify'
]

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CREDENTIALS_FILE = os.path.join(_ROOT, 'credentials.json')
TOKEN_FILE = os.path.join(_ROOT, 'token.pickle')

def get_google_credentials():
    """Get Google OAuth2 credentials for Calendar and Gmail access.

    On a hosted server (Render etc.) set GOOGLE_TOKEN_B64 env var to the
    base64-encoded contents of token.pickle — generated locally after first auth.
    """
    creds = None

    # Hosted path: load token from base64 env var (no filesystem write needed)
    token_b64 = os.getenv("GOOGLE_TOKEN_B64", "").strip()
    if token_b64:
        import base64, io
        creds = pickle.load(io.BytesIO(base64.b64decode(token_b64)))

    # Local path: load from file
    elif os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, 'rb') as f:
            creds = pickle.load(f)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_FILE):
                raise FileNotFoundError(
                    "credentials.json not found. Add it as a Secret File on Render "
                    "or run the OAuth flow locally first."
                )
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)

        # Save locally if possible (won't work on ephemeral servers but that's fine)
        try:
            with open(TOKEN_FILE, 'wb') as f:
                pickle.dump(creds, f)
        except OSError:
            pass

    return creds
