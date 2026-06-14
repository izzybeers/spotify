#%%
import json
import pandas as pd
import random
import numpy as np
import os
from pathlib import Path
from datetime import datetime
from spotify_helper_funs import get_song_info, write_to_supabase, update_supabase_rows, read_from_supabase, get_followed_playlists
from spotify_data_collection import data, sp, supabase, liked_songs

#%%

#%%
subscriptions = read_from_supabase(table_name = 'PlaylistSubscriptions')

def name_liked_songs_playlist(band_list):
    name = f"Liked songs from {', '.join(band_list[0:3])}{' and more' if len(band_list) > 3 else ''}"
    description = f"Liked songs from {', '.join(band_list)}"
    return [name, description]

def add_new_playlist(public, user_id, playlist_type, band_list, refresh, liked_songs):
    name, description = name_liked_songs_playlist(band_list)
    new_playlist = sp.current_user_playlist_create(name = name,
                                                   public = public,
                                                   collaborative = False,
                                                   description = description)
    new_subscription_id = random.randint(1, 1000000)
    data_to_write = pd.DataFrame({
        'id': [new_subscription_id],
        'user_id': [user_id],
        'playlist_type': [playlist_type],
        'playlist_id': [new_playlist['id']],
        'playlist_uri': [new_playlist['uri']],
        'band_list': ['|'.join(band_list)],
        'created_at': [pd.Timestamp.now(tz='UTC').isoformat()],
        'subscription_updated_at': [pd.Timestamp.now(tz='UTC').isoformat()],
        'playlist_updated_at': [pd.Timestamp.now(tz='UTC').isoformat()],
        'Active': [1],
        'refresh': [refresh],
        'public': [public]
    })
    write_to_supabase(table_name = 'PlaylistSubscriptions', df = data_to_write)
    
    liked_songs_from_artists = liked_songs[liked_songs['artist'].isin(band_list)]\
    .assign(display_name = lambda x: x['artist'] +  '-' + x['track'])\
        .sort_values(by = 'added_at', ascending = False)\
            .drop_duplicates(subset = 'display_name', keep = 'first')
    update_playlist(subscription_id = new_subscription_id,
                    new_songs = liked_songs_from_artists['uri'],
                    remove = True)
    return new_subscription_id

def update_playlist(subscription_id, new_songs, remove = False):
    playlist_id = read_from_supabase(table_name = 'PlaylistSubscriptions',
                                 select = 'playlist_id',
                                 eq_col_name = 'id',
                                 eq_value = subscription_id).iloc[0]['playlist_id']
    songs_on_playlist = set()
    start_indx = 0
    while True:
        songs_on_playlist_dict = sp.playlist_items(playlist_id = playlist_id, limit = 50, offset = start_indx)
        res = [item['item']['uri'] for item in songs_on_playlist_dict['items'] if item['item']['uri'] is not None]
        songs_on_playlist.update(res)
        if len(res) == 50:
            start_indx+=50
        else:
            break
    songs_to_add = set(new_songs) - songs_on_playlist
    if len(songs_to_add) > 0:
        try:
            for i in range(np.ceil(len(songs_to_add)/100).astype(int)):
                start_idx = i*100
                end_idx = min(start_idx + 100, len(songs_to_add))
                sp.playlist_add_items(playlist_id = playlist_id,
                                    items = list(songs_to_add)[start_idx:end_idx])
            print(f"Added {len(songs_to_add)} songs to playlist")
            update_supabase_rows(table_name = 'PlaylistSubscriptions',
                         match_column = 'id',
                         match_column_value = subscription_id,
                         new_row = {'playlist_updated_at': pd.Timestamp.now(tz='UTC').isoformat()})
        except Exception as e:
            print(f"Error adding tracks: {e}")
    if remove:   
        songs_to_remove = songs_on_playlist - set(new_songs)
        if len(songs_to_remove) > 0:
            try:
                for i in range(np.ceil(len(songs_to_remove)/100).astype(int)):
                    start_idx = i*100
                    end_idx = min(start_idx + 100, len(songs_to_remove))
                    sp.playlist_remove_all_occurrences_of_items(playlist_id = playlist_id,
                                                                items = list(songs_to_remove)[start_idx:end_idx])
                print(f"Removed {len(songs_to_remove)} songs from playlist")
                update_supabase_rows(table_name = 'PlaylistSubscriptions',
                            match_column = 'id',
                            match_column_value = subscription_id,
                            new_row = {'playlist_updated_at': pd.Timestamp.now(tz='UTC').isoformat()})
            except Exception as e:
                print(f"Error removing tracks")
    else:
        songs_to_remove = []
    if (len(songs_to_add) == 0) & (len(songs_to_remove) == 0):
        print(f"No updates for {subscription_id}")


def update_subscription_refresh_rate(subscription_id, new_refresh):
    update_supabase_rows(table_name = 'PlaylistSubscriptions',
                         match_column = 'id',
                         match_column_value = subscription_id,
                         new_row = {'refresh': new_refresh, 'subscription_updated_at': pd.Timestamp.now(tz='UTC').isoformat()})
    
def update_subscription_band_list(subscription_id, new_band_list, liked_songs):
    liked_songs_from_artists = liked_songs[liked_songs['artist'].isin(new_band_list)]\
    .assign(display_name = lambda x: x['artist'] +  '-' + x['track'])\
        .sort_values(by = 'added_at', ascending = False)\
            .drop_duplicates(subset = 'display_name', keep = 'first')
    update_supabase_rows(table_name = 'PlaylistSubscriptions',
                            match_column = 'id',
                            match_column_value = subscription_id,
                            new_row = {'band_list': '|'.join(new_band_list), 'subscription_updated_at': pd.Timestamp.now(tz='UTC').isoformat()})
    playlist_id = read_from_supabase(table_name = 'PlaylistSubscriptions',
                                 select = 'playlist_id',
                                 eq_col_name = 'id',
                                 eq_value = subscription_id).iloc[0]['playlist_id']
    name, description = name_liked_songs_playlist(new_band_list)
    sp.playlist_change_details(playlist_id = playlist_id, name = name, description = description)
    update_playlist(subscription_id = subscription_id,
                    new_songs = liked_songs_from_artists['uri'],
                    remove = True)

def update_subscription_playlist_publicity(subscription_id, new_playlist_publicity):
    update_supabase_rows(table_name = 'PlaylistSubscriptions',
                            match_column = 'id',
                            match_column_value = subscription_id,
                            new_row = {'public': new_playlist_publicity, 'subscription_updated_at': pd.Timestamp.now(tz='UTC').isoformat()})

def deactivate_subscription(subscription_id, unfollow = True):
    playlist_id = read_from_supabase(table_name = 'PlaylistSubscriptions',
                                     select = 'playlist_id',
                                     eq_col_name = 'id',
                                     eq_value = subscription_id).iloc[0]['playlist_id']
    if unfollow:
        sp.current_user_unfollow_playlist(playlist_id)
    update_supabase_rows(table_name = 'PlaylistSubscriptions',
                         match_column = 'id',
                         match_column_value = subscription_id,
                         new_row = {'Active': False, 'subscription_updated_at': pd.Timestamp.now(tz='UTC').isoformat()})

def reactivate_subscription(subscription_id):
    try:
        res = read_from_supabase(table_name = 'PlaylistSubscriptions',
                                 select = 'playlist_id',
                                 eq_col_name = 'id',
                                 eq_value = subscription_id).iloc[0]
        playlist_id = res['playlist_id']
        sp.current_user_follow_playlist(playlist_id)
        followed_playlists = get_followed_playlists()
        if playlist_id in followed_playlists:
            print('Successfully re-followed playlist')
        else:
            print('Error refollowing playlist')
        update_supabase_rows(table_name = 'PlaylistSubscriptions',
                            match_column = 'id',
                            match_column_value = subscription_id,
                            new_row = {'Active': True, 'subscription_updated_at': pd.Timestamp.now(tz='UTC').isoformat()})
    except Exception as e:
        print(f"Error reactivating subscription: {e}")
    
#%%

#%%
#artist liked songs playlists:


# subscription_id = 341846
# this_sub = subscriptions[subscriptions['id'] == subscription_id]
# artists = this_sub['band_list'].str.split('|')[0]

# artists.append('Architects')
# update_subscription_band_list(subscription_id = this_sub['id'][0],
#                                 new_band_list = artists,
#                                 liked_songs = liked_songs)


# artists.remove('Architects')
# update_subscription_band_list(subscription_id = this_sub['id'][0],
#                                 new_band_list = artists,
#                                 liked_songs = liked_songs)





#create new:
# new_subscription_id = add_new_playlist(name = name,
#                                        description = description,
#                                        public = True,
#                                        user_id = sp.current_user()['id'],
#                                        playlist_type = 'LikedSongsMultiBands',
#                                        band_list = '|'.join(artists),
#                                        refresh = 'hourly',
#                                        public = public)

#add/remove songs:




#do this later:
# sp.playlist_upload_cover_image





#%%

