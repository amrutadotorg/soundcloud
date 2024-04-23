import soundcloud
import json
import urllib.request, urllib.error, urllib.parse
import requests
import pathlib, importlib, os
from DB import mysqldb

# Existing functions remain unchanged

def sc_creds_db(what):
    cnx =  mysqldb('nvp')
    cur = cnx.cursor()
    cur.execute(f"SELECT CAST(JSON_EXTRACT(content, '$.{what}') AS CHAR) from nvp.creds where filename='sc_token.json'")
    cred = cur.fetchone()[0]
    cnx.close()
    return cred.replace('"','')

def sc_creds_db_update(response):
    cnx =  mysqldb('nvp')
    cur = cnx.cursor()
    cur.execute("update creds set content=%s where filename='sc_token.json'", [json.dumps(response)])
    cnx.close()

def sc_refresh_token():
    CLIENT_ID = ""
    CLIENT_SECRET = ""
    DOMAIN = 'api.soundcloud.com'

    base_url = f'https://{DOMAIN}'
    url = f"{base_url}/oauth2/token"

    # Create a temporary client instance to generate code_verifier and code_challenge
    temp_client = soundcloud.Client(client_id=CLIENT_ID, client_secret=CLIENT_SECRET)
    code_verifier = temp_client._generate_code_verifier()
    code_challenge = temp_client._generate_code_challenge(code_verifier)
    data = {
        'grant_type': 'refresh_token',
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'code_verifier': code_verifier,
        'refresh_token': sc_creds_db('refresh_token'),
        'code_challenge': code_challenge,
        'code_challenge_method': 'S256'
    }

    headers = {
        'Content-Type': "application/x-www-form-urlencoded",
        'accept': "application/json; charset=utf-8",
    }

    r = requests.post(url, headers=headers, data=urllib.parse.urlencode(data))
    response = r.json()

    if response.get('access_token'):
        sc_creds_db_update(response)
        print('Refreshing sc token successful')
        return sc_creds_db('access_token')
    else:
        print('There was an error refreshing your access token')
        print(r.text)

def sc_client():
    try:
        client = soundcloud.Client(access_token=sc_creds_db('access_token'))
        client.get('/me')
        print('Successfully authenticated with existing token')
    except Exception as e:
        print('!!!!!', e)
        client = soundcloud.Client(access_token=sc_refresh_token())
        print('Successfully refreshed token and authenticated')
    return client


def sc_client_simple():
    return sc_client()

def sc_client_simple_OLD():
    return soundcloud.Client(client_id=YOUR_CLIENT_ID)

def get_playlist_by_ID(client, ID):
    try :
        return client.get('/playlists/{}'.format(ID), representation = 'compact')
    except Exception as e:
        print(e)
        return None

def get_url_from_track(ID):
    client = sc_client_simple()
    try :
        track = client.get('/tracks/{}'.format(ID))
        return track.permalink_url
    except Exception as e:
        print(e)
        return None

def sc_get_tracks(playlistid):
    result = []
    playlist = client.get('/playlists/{}'.format(playlistid))

    for track in playlist.tracks:
        result.append([track['id'], track['title']])
    return result


def sc_get_tracks_full(playlistid):
    result = []
    playlist = client.get('/playlists/{}'.format(playlistid))

    for track in playlist.tracks:
        result.append(track)
    return result



def getTrackIdByUri(uri):
        tracks = client.get("/me/tracks", limit=200)
        for track in tracks:
            if track.permalink_url==uri:
                return track.id, track.title
        return None, None



def sc_upd_playlist(playlistid, new_tracks):
    try :
        new_tracks = [dict(id=id) for id in new_tracks]
        to_playlist = client.get('/playlists/{}'.format(playlistid))
        client.put(to_playlist.uri, playlist={ 'tracks': new_tracks  })
    except Exception as e:
        print(e)

def sc_update_track_title(trackid, title):
    track = client.get('/tracks/{}'.format(trackid))
    client.put(track.uri, track={
          'title': title
    })


client = sc_client()
def sc_update_track_title_v2(client, trackid, title):
    return client.put('/tracks/' + str(trackid), track={
          'title': title
    })


def sc_update_playlist_title(client, playlistid, title):
#    track = client.get('/playlists/{}'.format(playlistid))
    client.put('/playlists/' + str(playlistid), playlist={ 'title': title })

def sc_download(track_id, path):
 track_id = str(track_id)
 track_info = client.get('/tracks/' + track_id)
 track = client.get('/tracks/' + track_id + '/stream', allow_redirects=False)
 url = track.location
 if track_info.description : file_name=track_info.description
 else : file_name = track_id + '.mp3'
 u = urllib.request.urlopen(url)
 f = open(path+file_name, 'wb')
 meta = u.info()
 file_size = int(meta.getheaders("Content-Length")[0])
 print("Downloading: %s Bytes: %s" % (file_name, file_size))

 file_size_dl = 0
 block_sz = 8192
 while True:
    buffer = u.read(block_sz)
    if not buffer:
        break

    file_size_dl += len(buffer)
    f.write(buffer)
    status = r"%10d  [%3.2f%%]" % (file_size_dl, file_size_dl * 100. / file_size)
    status = status + chr(8)*(len(status)+1)
    print(status, end=' ')

 f.close()
 return file_name


def sc_download2(track_id, path):
 track_info = client.get('/tracks/' + str(track_id))
 track = client.get('/tracks/' + str(track_id) + '/download', allow_redirects=False)
 url = track.url
 if track_info.description : file_name=track_info.description
 else : file_name = track_id
 u = urllib.request.urlopen(url)
 f = open(path+file_name, 'wb')
 meta = u.info()
 file_size = int(meta.getheaders("Content-Length")[0])
 print("Downloading: %s Bytes: %s" % (file_name, file_size))

 file_size_dl = 0
 block_sz = 8192
 while True:
    buffer = u.read(block_sz)
    if not buffer:
        break

    file_size_dl += len(buffer)
    f.write(buffer)
    status = r"%10d  [%3.2f%%]" % (file_size_dl, file_size_dl * 100. / file_size)
    status = status + chr(8)*(len(status)+1)
    print(status, end=' ')

 f.close()
 return file_name

def sc_talk_to_top(sc_set_from_id):
  tracks2 = sc_get_tracks( sc_set_from_id )
  found = [i for i, e in enumerate(tracks2) if 'Talk' in e[1] and 'DP' in e[1]]
  if len(found)==1 and found[0]>0:
        tracks2.insert(0, tracks2.pop(found[0]))
        tracksIDS_from = [track[0] for track in tracks2]
        sc_upd_playlist(sc_set_from_id, tracksIDS_from)
        print('list updated DP talk found')

  else :
    found2 = [i for i, e in enumerate(tracks2) if 'Talk' in e[1] ]

    if len(found2)==1 and found2[0]>0:
        tracks2.insert(0, tracks2.pop(found2[0]))
        tracksIDS_from = [track[0] for track in tracks2]
        sc_upd_playlist(sc_set_from_id, tracksIDS_from)
        print('list updated non DP talk found')
