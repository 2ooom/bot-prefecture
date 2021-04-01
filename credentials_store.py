import os
import json
import logging
from utils import get_json_file_content

import google.auth
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import id_token

class CredentialsStore:
    def __init__(self, secrets_path, credentials_path):
        self.oauth_secrets = get_json_file_content(secrets_path)['web']
        self.credentials_path = credentials_path
        self.logger = logging.getLogger(f"CredentialsStore")

    def get_credentials(self, email):
        credentials_store = get_json_file_content(self.credentials_path)
        if email not in credentials_store:
            raise Exception(f'Credentials for email {email} are not found')
        cred = credentials_store[email]

        return google.oauth2.credentials.Credentials(
            cred['token'],
            refresh_token=cred['refresh_token'],
            token_uri=self.oauth_secrets['token_uri'],
            client_id=self.oauth_secrets['client_id'],
            client_secret=self.oauth_secrets['client_secret'])

    def update_credentials(self, credentials):
        self.logger.debug('Validating claims of access token')
        claims = id_token.verify_oauth2_token(credentials.id_token, GoogleRequest(), credentials.client_id)
        email = claims['email']
        self.logger.info(f"Saving offline credentials for {email}")
        credentials_store = {}
        if os.path.exists(self.credentials_path):
            credentials_store = get_json_file_content(self.credentials_path)

        credentials_store[email] = {
            'token': credentials.token,
            'refresh_token': credentials.refresh_token
        }
        with open(self.credentials_path, 'w') as f:
            f.write(json.dumps(credentials_store))
        return email