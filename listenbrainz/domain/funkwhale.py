import time
import base64
from typing import Optional, List
from urllib.parse import urlencode
from datetime import datetime

import requests
from requests_oauthlib import OAuth2Session
from oauthlib.oauth2.rfc6749.errors import InvalidGrantError

from flask import current_app, session

from listenbrainz.db import funkwhale as db_funkwhale
from listenbrainz.webserver import db_conn
from listenbrainz.domain.external_service import ExternalServiceError, ExternalServiceAPIError, ExternalServiceInvalidGrantError

import sqlalchemy

FUNKWHALE_API_RETRIES = 5

class FunkwhaleService:
    def __init__(self):
        self.redirect_url = current_app.config.get('FUNKWHALE_CALLBACK_URL', 
                                                   current_app.config['SERVER_ROOT_URL'] + '/settings/music-services/funkwhale/callback/')

    def _get_or_create_oauth_credentials(self, host_url: str, client_id: str = None, client_secret: str = None, scopes: str = None) -> tuple:
        # Try to get server by host_url
        server = db_funkwhale.get_server_by_host_url(host_url)
        if server and server.get('client_id') and server.get('client_secret'):
            return server['client_id'], server['client_secret'], server['id']
        # If not found or missing credentials, create
        if not (client_id and client_secret and scopes):
            raise ExternalServiceError("Missing client_id, client_secret, or scopes for new Funkwhale server registration.")
        server_id = db_funkwhale.get_or_create_server(host_url, client_id, client_secret, scopes)
        return client_id, client_secret, server_id

    def get_user(self, user_id: int, host_url: str = None, refresh: bool = False) -> Optional[dict]:
        # Get server by host_url
        if not host_url:
            return None
        server = db_funkwhale.get_server_by_host_url(host_url)
        if not server:
            return None
        token = db_funkwhale.get_token(user_id, server['id'])
        if not token:
            return None
        user = {
            'user_id': user_id,
            'host_url': host_url,
            'client_id': server['client_id'],
            'client_secret': server['client_secret'],
            'access_token': token['access_token'],
            'refresh_token': token['refresh_token'],
            'token_expiry': token['token_expiry'],
            'funkwhale_server_id': server['id']
        }
        if refresh and self.user_oauth_token_has_expired(user):
            user = self.refresh_access_token(user_id, host_url, user['refresh_token'])
        return user

    def add_new_user(self, user_id: int, host_url: str, token: dict, client_id: str, client_secret: str, scopes: str) -> bool:
        access_token = token['access_token']
        refresh_token = token['refresh_token']
        expires_at = int(time.time()) + token['expires_in']
        token_expiry_datetime = datetime.fromtimestamp(expires_at)
        # Get user details from Funkwhale API
        headers = {'Authorization': f'Bearer {access_token}'}
        response = requests.get(f"{host_url}/api/v1/users/me", headers=headers)
        if response.status_code != 200:
            raise ExternalServiceError(f"Could not get user details from Funkwhale: {response.text}")
        # Register or get server
        client_id, client_secret, server_id = self._get_or_create_oauth_credentials(host_url, client_id, client_secret, scopes)
        # Save token
        db_funkwhale.save_token(user_id, server_id, access_token, refresh_token, token_expiry_datetime)
        return True

    def get_authorize_url(self, host_url: str, scopes: List[str], state: Optional[str] = None) -> str:
        # Ensure host_url doesn't end with a slash
        host_url = host_url.rstrip('/')
        # Check if server exists
        server = db_funkwhale.get_server_by_host_url(host_url)
        if server and server.get('client_id') and server.get('client_secret'):
            client_id = server['client_id']
        else:
            # Create OAuth app on Funkwhale
            app_data = {
                'name': 'ListenBrainz',
                'website': host_url,
                'redirect_uris': self.redirect_url,
                'scopes': ' '.join(scopes)
            }
            response = requests.post(f"{host_url}/api/v1/oauth/apps/", json=app_data, timeout=30)
            if response.status_code != 201:
                raise ExternalServiceError(f"Failed to create OAuth app: {response.status_code} - {response.text}")
            app_credentials = response.json()
            client_id = app_credentials['client_id']
            client_secret = app_credentials['client_secret']
            db_funkwhale.get_or_create_server(host_url, client_id, client_secret, ' '.join(scopes))
        auth_url = f"{host_url}/api/v1/oauth/authorize"
        oauth = OAuth2Session(
            client_id=client_id,
            redirect_uri=self.redirect_url,
            scope=scopes,
            state=state
        )
        authorization_url, _ = oauth.authorization_url(auth_url)
        return authorization_url

    def fetch_access_token(self, code: str):
        host_url = session.get('funkwhale_host_url')
        if not host_url:
            raise ExternalServiceError("No host URL found in session")
        server = db_funkwhale.get_server_by_host_url(host_url)
        if not server:
            raise ExternalServiceError("No Funkwhale server found for host_url")
        client_id = server['client_id']
        client_secret = server['client_secret']
        oauth = OAuth2Session(
            client_id=client_id,
            redirect_uri=self.redirect_url
        )
        token_url = f"{host_url}/api/v1/oauth/token/"
        try:
            return oauth.fetch_token(
                token_url,
                client_secret=client_secret,
                code=code,
                include_client_id=True
            )
        except requests.exceptions.RequestException as e:
            raise ExternalServiceError(f"Failed to fetch access token: {str(e)}")
        except InvalidGrantError as e:
            raise ExternalServiceInvalidGrantError("Invalid authorization code") from e

    def refresh_access_token(self, user_id: int, host_url: str, refresh_token: str):
        server = db_funkwhale.get_server_by_host_url(host_url)
        if not server:
            raise ExternalServiceError("No Funkwhale server found for host_url")
        client_id = server['client_id']
        client_secret = server['client_secret']
        oauth = OAuth2Session(
            client_id=client_id,
            redirect_uri=self.redirect_url
        )
        token_url = f"{host_url}/api/v1/oauth/token/"
        try:
            token = oauth.refresh_token(
                token_url,
                client_secret=client_secret,
                refresh_token=refresh_token,
                include_client_id=True
            )
        except InvalidGrantError as e:
            raise ExternalServiceInvalidGrantError("User revoked access") from e
        except requests.exceptions.RequestException as e:
            raise ExternalServiceAPIError(f"Could not connect to Funkwhale server: {str(e)}")
        access_token = token['access_token']
        if "refresh_token" in token:
            refresh_token = token['refresh_token']
        expires_at = int(time.time()) + token['expires_in']
        token_expiry_datetime = datetime.fromtimestamp(expires_at)
        db_funkwhale.update_token(user_id, server['id'], access_token, refresh_token, token_expiry_datetime)
        return self.get_user(user_id, host_url)

    def revoke_user(self, user_id: int, host_url: str):
        server = db_funkwhale.get_server_by_host_url(host_url)
        if not server:
            return
        db_funkwhale.delete_token(user_id, server['id'])

    def remove_user(self, user_id: int):
        # Remove all tokens for this user across all servers
        db_conn.execute(sqlalchemy.text("""
            DELETE FROM funkwhale_tokens WHERE user_id = :user_id
        """), {'user_id': user_id})
        db_conn.commit()

    def user_oauth_token_has_expired(self, user: dict) -> bool:
        from datetime import timezone
        token_expiry = user['token_expiry']
        if isinstance(token_expiry, datetime):
            now = datetime.now(timezone.utc)
            if token_expiry.tzinfo is None:
                token_expiry = token_expiry.replace(tzinfo=timezone.utc)
            return now >= token_expiry
        else:
            return int(time.time()) >= token_expiry