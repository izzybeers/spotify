import pandas as pd
from supabase import create_client, Client
from datetime import datetime
import os
import spotipy
from spotipy.oauth2 import SpotifyOAuth

supabase_api_key = 'sb_publishable_CRS7gXJPt2eGRZ2QyfMHWQ_tFqFZcSj'
supabase_endpoint= 'https://vciwmitbqbfjcrrxgcmb.supabase.co'
supabase: Client = create_client(supabase_endpoint, supabase_api_key)
CLIENT_ID = "4e8269446f474d3f920be9dfa56086d5"
CLIENT_SECRET = "69f0f2b62b924d458d14a45a526cd5ed"
REDIRECT_URI = "http://127.0.0.1:9090/callback" # Must match your Spotify Dashboard

def get_song_info(uri_list, sp):
    all_track_info = pd.DataFrame()
    for song in uri_list:
        print(song)
        track = sp.track(song)
        track_info = pd.DataFrame({
            'uri': [song],
            'title': [track['name']],
            'release_date': [track['album']['release_date']],
            'song_duration_mins': [track['duration_ms']/60000],
            'album': [track['album']['name']],
            'album_image': [track['album']['images'][0]['url']],
            'album_uri': [track['album']['uri']],
            'album_id': [track['album']['id']],
            'album_type': [track['album']['album_type']],
            'artist': [track['album']['artists'][0]['name']],
            'artist_uri': [track['album']['artists'][0]['uri']],
            'artist_id': [track['album']['artists'][0]['id']],
            'collaborator_artists': [', '.join([artist['name'] for artist in track['album']['artists'][1:]])]
    })
        all_track_info = pd.concat([all_track_info, track_info], axis = 0)
    
    try:
        all_track_info['display_name'] = all_track_info['artist'] + ' - ' + all_track_info['title']
        all_track_info['added_at'] = datetime.now().isoformat()
        return all_track_info
    except Exception as e:
        print(f"Error pulling track info: {e}")
        print(all_track_info.head())

def write_to_supabase(table_name, df):
    data_to_insert = df.to_dict(orient='records')
    try:
        response = supabase.table(table_name).insert(data_to_insert).execute()
        print(f"Successfully inserted {len(response.data)} rows.")
    except Exception as e:
        print(f"Error inserting data: {e}")

def update_supabase_rows(table_name, match_column, match_column_value, new_row):
    try:
        response = supabase.table(table_name).update(new_row).eq(match_column, match_column_value).execute()
        print(f"Successfully updated {len(response.data)} rows.")
    except Exception as e:
        print(f"Error inserting data: {e}")

def delete_from_supabase(table_name, eq_column_name, eq_value):
    try:
        delete_result = supabase.table('PlaylistSubscriptions').delete().eq(eq_column_name, eq_value).execute()
        print(f"Successfully deleted test subscription: {eq_column_name} {eq_value}")
    except Exception as e:
        print(f"Error deleting data: {e}")

def read_from_supabase(table_name, select = '*', eq_col_name = None, eq_value = None, chunk_size = None):
    if chunk_size is not None:
        df_results = pd.DataFrame()
        start_indx = 0
        while True:
            if eq_col_name is None:
                res = pd.DataFrame(supabase.table(table_name).select(select).range(start_indx, start_indx + chunk_size-1).execute().data)
            else:
                res = pd.DataFrame(supabase.table(table_name).select(select).eq(eq_col_name, eq_value).range(start_indx, start_indx + chunk_size-1).execute().data)
            df_results = pd.concat([df_results, res])
            if len(res) < chunk_size:
                break
            else:
                start_indx = start_indx + chunk_size
        return df_results
    else:
        if eq_col_name is None:
            return(pd.DataFrame(supabase.table(table_name).select(select).execute().data))
        else:
            return(pd.DataFrame(supabase.table(table_name).select(select).eq(eq_col_name, eq_value).execute().data))
        
def get_followed_playlists(sp):
    followed_playlists = pd.DataFrame()
    offset = 0
    while True:
        res = sp.current_user_playlists(limit = 50, offset = offset)
        res_to_add = [{'id': item['id'], 'name': item['name']} for item in res['items']]
        followed_playlists = pd.concat([followed_playlists, pd.DataFrame(res_to_add)], axis = 0)
        if len(res_to_add) == 50:
            offset += 50
        else:
            break
    return followed_playlists

def get_readable_playlists(sp):
    followed_playlists = get_followed_playlists(sp)
    readable = []
    for f in range(len(followed_playlists)):
        try:
            get_first_song = sp.playlist_items(playlist_id = followed_playlists['id'].iloc[f], limit = 1, offset = 0)
            readable.append({
                'id': followed_playlists['id'].iloc[f],
                'name': followed_playlists['name'].iloc[f]
            })
        except Exception as e:
            pass
    return pd.DataFrame(readable)

def get_songs_on_playlist(playlist_id, sp):
    songs_on_playlist = pd.DataFrame()
    start_indx = 0
    while True:
        songs_on_playlist_dict = sp.playlist_items(playlist_id = playlist_id, limit = 50, offset = start_indx)
        res = [{'uri': item['item']['uri'],
                'name': item['item']['name'],
                'artist': item['item']['artists'][0]['name']} for item in songs_on_playlist_dict['items'] if item['item']['uri'] is not None]
        songs_on_playlist = pd.concat([songs_on_playlist, pd.DataFrame(res)])
        if len(res) == 50:
            start_indx+=50
        else:
            break
    return songs_on_playlist