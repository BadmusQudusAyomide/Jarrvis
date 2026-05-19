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

CREDENTIALS_FILE = r'C:\Users\HP\Documents\Jarvis\credentials.json'
TOKEN_FILE = r'C:\Users\HP\Documents\Jarvis\token.pickle'

def get_google_credentials():
    """Get Google OAuth2 credentials for Calendar and Gmail access.
    
    Returns:
        Credentials: Authenticated Google credentials object
        
        
    Process:
    1. First run - opens browser for OAuth2 consent
    2. Subsequent runs - loads token from file, refreshes if expired
    """
    creds = None
    
    # Load existing credentials from token file
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, 'rb') as f:
            creds = pickle.load(f)
    
    # If credentials are invalid or missing, get new ones
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            # Refresh expired credentials
            creds.refresh(Request())
        else:
            # Run OAuth2 flow for new credentials
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        
        # Save credentials for future use
        with open(TOKEN_FILE, 'wb') as f:
            pickle.dump(creds, f)
    
    return creds
