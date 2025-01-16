import json
import sys
from datetime import datetime, timedelta, timezone

import requests
from loguru import logger

import soundcloud
from DB3 import Database, DatabaseError

logger.remove()
logger.add(sink=lambda message: print(message), level="INFO")


class SoundCloudClient:
    def __init__(self):
        self.client_id = ""
        self.client_secret = ""
        self.redirect_uri = "/"
        self.api_domain = "api.soundcloud.com"
        self.auth_domain = "secure.soundcloud.com"  # New auth domain
        self.token_filename = "sc_token.json"
        self._client = None
        logger.debug("Initialized SoundCloudClient instance.")

    def _sc_creds_db(self, what: str) -> str:
        logger.debug(f"Fetching {what} from database.")
        try:
            with Database("nvp") as db:
                query = f"SELECT CAST(JSON_EXTRACT(content, '$.{what}') AS CHAR) FROM nvp.creds WHERE filename='{self.token_filename}'"
                result = db.execute_query(query)
                if result and len(result) > 0:
                    cred = result[0][0]
                    logger.debug(f"Successfully retrieved {what} from database.")
                    return cred.replace('"', "")
                else:
                    logger.error(f"No credentials found for {what}")
                    raise DatabaseError(f"No credentials found for {what}")
        except DatabaseError as e:
            logger.error(f"Database error: {e}")
            raise

    def _sc_creds_db_update(self, response: dict) -> None:
        logger.debug("Updating SoundCloud token in the database.")
        try:
            with Database("nvp") as db:
                query = "UPDATE creds SET content=%s WHERE filename=%s"
                db.execute_query(query, (json.dumps(response), self.token_filename))
                logger.debug("SoundCloud token successfully updated in the database.")
        except DatabaseError as e:
            logger.error(f"Database error while updating token: {e}")
            raise

    def _sc_refresh_token(self) -> str:
        logger.debug("Refreshing SoundCloud token.")
        import urllib.parse

        # Updated token endpoint
        url = f"https://{self.auth_domain}/oauth/token"
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "accept": "application/json; charset=utf-8",
        }

        data = {
            "grant_type": "refresh_token",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": self._sc_creds_db("refresh_token"),
        }

        try:
            r = requests.post(url, headers=headers, data=urllib.parse.urlencode(data))
            response = r.json()

            if response.get("access_token"):
                # Calculate the expiry time
                expires_in = response.get("expires_in", 0)
                self.expiry_time = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
                response["expiry"] = self.expiry_time.isoformat()

                self._sc_creds_db_update(response)
                logger.debug("SoundCloud token refreshed and updated.")
                return response["access_token"]
            else:
                logger.error(f"Failed to refresh token: {r.text}")
                raise Exception("Failed to refresh SoundCloud token")
        except Exception as e:
            logger.error(f"Error during token refresh: {e}")
            raise

    def _get_credentials(self):
        logger.debug("Fetching SoundCloud credentials from the database.")
        try:
            with Database("nvp") as db:
                query = f"SELECT content FROM nvp.creds WHERE filename='{self.token_filename}'"
                result = db.execute_query(query)
                if result and len(result) > 0:
                    credentials = json.loads(result[0][0])
                    self.access_token = credentials.get("access_token")
                    expiry_str = credentials.get("expiry")
                    if expiry_str:
                        self.expiry_time = datetime.fromisoformat(expiry_str)
                        logger.debug(f"Retrieved credentials: access_token exists, expiry at {self.expiry_time}")
                    else:
                        logger.error("Expiry information not found in credentials.")
                else:
                    logger.error("No credentials found in the database.")
                    raise DatabaseError("No credentials found")
        except Exception as e:
            logger.error(f"Error fetching credentials: {e}")
            raise

    @property
    def client(self):
        """Gets the authenticated SoundCloud client."""
        if self._client is None:
            logger.debug("Creating SoundCloud client.")
            self._client = self.sc_client()
        return self._client

    def __getattr__(self, name):
        """Redirects attribute access to the underlying SoundCloud client."""
        if self._client is None:
            self.client
        return getattr(self._client, name)

    def sc_client(self):
        """Ensures the client is authenticated and returns the SoundCloud client."""
        logger.debug("Creating SoundCloud client.")
        try:
            # Ensure credentials are loaded
            self._get_credentials()

            # Check if token is expired
            if self.expiry_time and datetime.now(timezone.utc) >= self.expiry_time:
                logger.debug("Token has expired, refreshing it.")
                self.access_token = self._sc_refresh_token()

            # Updated client initialization with new parameters
            client = soundcloud.Client(
                access_token=self.access_token,
                host=self.api_domain,
                auth_host=self.auth_domain
            )
            client.get("/me")  # Test the connection
            logger.debug("SoundCloud client successfully created.")
            return client
        except Exception as e:
            logger.error(f"Error creating SoundCloud client: {e}")
            logger.debug("Attempting to refresh token and create client.")
            self.access_token = self._sc_refresh_token()
            client = soundcloud.Client(
                access_token=self.access_token,
                host=self.api_domain,
                auth_host=self.auth_domain
            )
            return client

    def sc_upd_playlist2(self, playlist_id: int, new_track_ids: list):
        """Updates the specified SoundCloud playlist with new track IDs."""
        try:
            # Ensure we have an active client
            client = self.sc_client()

            # Format the track IDs into the required structure
            new_tracks = [{"id": track_id} for track_id in new_track_ids]

            # Updated playlist URI to use the api_domain
            to_playlist_uri = f"https://{self.api_domain}/playlists/{playlist_id}"

            # Send the request to update the playlist with new tracks
            response = client.put(to_playlist_uri, playlist={"tracks": new_tracks})

            logger.info(f"Playlist {playlist_id} updated successfully.")
            return response
        except Exception as e:
            logger.error(f"Error updating playlist {playlist_id}: {e}")
            raise

    def get_playlist_by_ID(self, playlist_id: int):
        """Fetches the details of a playlist by its ID."""
        try:
            client = self.sc_client()
            playlist = client.get(f"/playlists/{playlist_id}")
            return playlist
        except Exception as e:
            logger.error(f"Error fetching playlist {playlist_id}: {e}")
            raise

    def sc_get_tracks_ids(self, playlist_id: int):
        """Fetches the track IDs of a given playlist."""
        try:
            client = self.sc_client()
            playlist = client.get(f"/playlists/{playlist_id}", representation="id")
            track_ids = [track["id"] for track in playlist.tracks]
            print(f"Track IDs in Playlist {playlist_id}: {track_ids}")
            return track_ids
        except Exception as e:
            logger.error(f"Error fetching track IDs for playlist {playlist_id}: {e}")
            raise
