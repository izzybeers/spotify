#%%
import pytest
import pandas as pd
import sys
import os

#when running locally:
sys.path.append(os.path.abspath('..'))
from spotify_data_collection import sp, liked_songs
from spotify_helper_funs import write_to_supabase, update_supabase_rows, read_from_supabase, get_followed_playlists, get_songs_on_playlist, delete_from_supabase
from playlist_builder import add_new_playlist, update_playlist, update_subscription_refresh_rate, update_subscription_band_list, update_subscription_playlist_publicity, deactivate_subscription, reactivate_subscription

#%%

#%%
def test_create_change_remove_reactivate_multibandlikedsongs_playlist():
    user_id = sp.current_user()['id']
    user_name = sp.current_user()['name']
    band_list = ['All That Remains', 'Arch Enemy']
    print('Attempting to create playlist for All That Remains and Arch Enemy...')
    sub_id = add_new_playlist(playlist_type = 'LikedSongsMultiBands',
                              public = True,
                              user_id = user_id,
                              user_name = user_name,
                              band_list = band_list,
                              refresh = 'hourly',
                              liked_songs = liked_songs)
    try:
        assert sub_id is not None, 'Error - no sub id generated'

        #check supabase:
        supabase_result = read_from_supabase(table_name = 'PlaylistSubscriptions',
                                            eq_col_name = 'id',
                                            eq_value = sub_id)

        assert len(supabase_result) == 1, f"Error: supabase result generated {len(supabase_result)} rows"
        
        active = supabase_result['Active'].iloc[0]
        supabase_band_list = supabase_result['param_list'].iloc[0]
        refresh = supabase_result['refresh'].iloc[0]
        playlist_id = supabase_result['playlist_id'].iloc[0]
        public = supabase_result['public'].iloc[0]
        assert (active) & (supabase_band_list == 'All That Remains|Arch Enemy') & (refresh == 'hourly') & (playlist_id is not None) & (public) & (pd.to_datetime(supabase_result['created_at'][0]).round('min') == pd.to_datetime(supabase_result['subscription_updated_at'][0]).round('min')) & (pd.to_datetime(supabase_result['created_at'][0]).round('min') == pd.to_datetime(supabase_result['playlist_updated_at'][0]).round('min')),\
        "One of the values in supabase was unexpected."

        followed_playlists = get_followed_playlists(sp)
        assert playlist_id in followed_playlists['id'], 'Error: user is not following playlist.'

        playlist_info = sp.playlist(playlist_id)
        name = playlist_info['name']
        description = playlist_info['description']
        assert (name == f"Liked songs from All That Remains, Arch Enemy") & (description == 'Liked songs from All That Remains, Arch Enemy'), "Name or description is not correct."

        songs_on_playlist = get_songs_on_playlist(playlist_id, sp)
        num_songs_on_playlist = len(songs_on_playlist)
        assert num_songs_on_playlist > 0, "Error: no songs were added to playlist"

        new_band_list = band_list + ['Atreyu', 'Ariana Grande']
        print('\n\nAdding Atreyu and Ariana Grande to the playlist subscription to make sure Atreyu songs are added, and the fact that I have no liked songs from Ariana Grande does not cause an error.')

        update_subscription_band_list(sub_id, user_name, new_band_list, liked_songs)

        new_supabase_result = read_from_supabase(table_name = 'PlaylistSubscriptions',
                                                eq_col_name = 'id',
                                                eq_value = sub_id)

        assert len(new_supabase_result) == 1, f"Error: supabase result for new playlist generated {len(new_supabase_result)} rows"
        
        new_active = new_supabase_result['Active'].iloc[0]
        new_supabase_band_list = new_supabase_result['param_list'].iloc[0]
        new_refresh = new_supabase_result['refresh'].iloc[0]
        new_playlist_id = new_supabase_result['playlist_id'].iloc[0]
        new_public = new_supabase_result['public'].iloc[0]
        subscription_update_time_after_adding_bands = new_supabase_result['subscription_updated_at'].iloc[0]
        playlist_update_time_after_adding_bands = new_supabase_result['playlist_updated_at'].iloc[0]
        assert (new_active) & (new_supabase_band_list == 'All That Remains|Arch Enemy|Atreyu|Ariana Grande') & (new_refresh == 'hourly') & (new_playlist_id == playlist_id) & (new_public) & (new_supabase_result['created_at'][0] < subscription_update_time_after_adding_bands) & (new_supabase_result['created_at'][0] < playlist_update_time_after_adding_bands),\
        "One of the values in supabase for new playlist was unexpected."

        followed_playlists = get_followed_playlists(sp)
        assert playlist_id in followed_playlists['id'], 'Error: user is not following new playlist.'
            
        new_playlist_info = sp.playlist(playlist_id)
        new_name = new_playlist_info['name']
        new_description = new_playlist_info['description']
        assert (new_name == f"Liked songs from All That Remains, Arch Enemy, Atreyu and more") & (new_description == 'Liked songs from All That Remains, Arch Enemy, Atreyu, Ariana Grande'),\
        f"Name or description is not correct."
            
        songs_on_new_playlist = get_songs_on_playlist(playlist_id, sp)

        assert (len(songs_on_new_playlist) > len(songs_on_playlist)) & (songs_on_new_playlist['artist'].nunique() == 3),\
        'Number of songs or distinct artists on new playlist was unexpected.'

        new_trimmed_band_list = ['Atreyu', 'Arch Enemy']
        print('\n\nRemoving All That Remains and Ariana Grande from subscription.')

        update_subscription_band_list(sub_id, user_name, new_trimmed_band_list, liked_songs)

        trimmed_supabase_result = read_from_supabase(table_name = 'PlaylistSubscriptions',
                                                eq_col_name = 'id',
                                                eq_value = sub_id)

        assert len(trimmed_supabase_result) == 1, f"Error: supabase result for trimmed playlist generated {len(trimmed_supabase_result)} rows"

        trimmed_active = trimmed_supabase_result['Active'].iloc[0]
        trimmed_supabase_band_list = trimmed_supabase_result['param_list'].iloc[0]
        trimmed_refresh = trimmed_supabase_result['refresh'].iloc[0]
        trimmed_playlist_id = trimmed_supabase_result['playlist_id'].iloc[0]
        trimmed_public = trimmed_supabase_result['public'].iloc[0]
        subscription_update_time_after_removing_bands = trimmed_supabase_result['subscription_updated_at'].iloc[0]
        playlist_update_time_after_removing_bands = trimmed_supabase_result['playlist_updated_at'].iloc[0]
        assert (trimmed_active) & (trimmed_supabase_band_list == 'Atreyu|Arch Enemy') &(trimmed_refresh == 'hourly') & (trimmed_playlist_id == playlist_id) & (trimmed_public) & (trimmed_supabase_result['created_at'][0] < subscription_update_time_after_removing_bands) & (trimmed_supabase_result['created_at'][0] < playlist_update_time_after_removing_bands),\
        "One of the values in supabase for trimmed playlist was unexpected."


        followed_playlists = get_followed_playlists(sp)
        assert playlist_id in followed_playlists['id'], 'Error: user is not following trimmed playlist.'
            
        trimmed_playlist_info = sp.playlist(playlist_id)
        trimmed_name = trimmed_playlist_info['name']
        trimmed_description = trimmed_playlist_info['description']
        assert (trimmed_name == f"Liked songs from Atreyu, Arch Enemy") & (trimmed_description == 'Liked songs from Atreyu, Arch Enemy'),\
        f"Name or description for trimmed playlist is not correct."

        songs_on_trimmed_playlist = get_songs_on_playlist(playlist_id, sp)

        assert (len(songs_on_trimmed_playlist) < len(songs_on_new_playlist)) & (songs_on_trimmed_playlist['artist'].nunique() == 2),\
        'Number of songs or distinct artists on trimmed playlist was not expected.'

        #deactivate subscription

        print('\n\nDeactivating subscription...')

        deactivate_subscription(sub_id, unfollow = True)

        deactivated_supabase_result = read_from_supabase(table_name = 'PlaylistSubscriptions',
                                                        eq_col_name = 'id',
                                                        eq_value = sub_id)

        assert len(deactivated_supabase_result) == 1, f"Error: supabase result for deactivated playlist generated {len(deactivated_supabase_result)} rows"

        deactivated_active = deactivated_supabase_result['Active'].iloc[0]
        deactivated_supabase_band_list = deactivated_supabase_result['param_list'].iloc[0]
        deactivated_refresh = deactivated_supabase_result['refresh'].iloc[0]
        deactivated_playlist_id = deactivated_supabase_result['playlist_id'].iloc[0]
        deactivated_public = deactivated_supabase_result['public'].iloc[0]
        subscription_update_time_after_deactivating = deactivated_supabase_result['subscription_updated_at'].iloc[0]
        assert (not deactivated_active) & (deactivated_supabase_band_list == 'Atreyu|Arch Enemy') & (deactivated_refresh == 'hourly') & (deactivated_playlist_id == playlist_id) & (deactivated_public) & (deactivated_supabase_result['created_at'][0] < subscription_update_time_after_deactivating) & (subscription_update_time_after_removing_bands < subscription_update_time_after_deactivating),\
        "One of the values in supabase for deactivated playlist was unexpected."

        followed_playlists = get_followed_playlists(sp)
        assert playlist_id not in followed_playlists['id'], 'Error: User is still following the deactivated playlist'

        reactivate_subscription(sub_id)

        print('\n\nReactivating subscription...')

        reactivated_supabase_result = read_from_supabase(table_name = 'PlaylistSubscriptions',
                                                        eq_col_name = 'id',
                                                        eq_value = sub_id)

        assert len(reactivated_supabase_result) ==1, f"Error: supabase result generated for reactivated playlist {len(reactivated_supabase_result)} rows"
        reactivated_active = reactivated_supabase_result['Active'].iloc[0]
        reactivated_supabase_band_list = reactivated_supabase_result['param_list'].iloc[0]
        reactivated_refresh = reactivated_supabase_result['refresh'].iloc[0]
        reactivated_playlist_id = reactivated_supabase_result['playlist_id'].iloc[0]
        reactivated_public = reactivated_supabase_result['public'].iloc[0]
        subscription_update_time_after_reactivating = reactivated_supabase_result['subscription_updated_at'].iloc[0]
        assert (reactivated_active) & (reactivated_supabase_band_list == 'Atreyu|Arch Enemy') & (reactivated_refresh == 'hourly') & (reactivated_playlist_id == playlist_id) & (reactivated_public) & (reactivated_supabase_result['created_at'][0] < subscription_update_time_after_reactivating) & (subscription_update_time_after_deactivating < subscription_update_time_after_reactivating),\
        "One of the  values in supabase for reactivated playlist was unexpected."

        followed_playlists = get_followed_playlists(sp)
        assert playlist_id in followed_playlists['id'], 'Error: user is not following reactivated playlist.'
    
    finally:
        deactivate_subscription(sub_id, unfollow = True)
        delete_from_supabase('PlaylistSubscriptions', 'id', sub_id)

#%%







# %%
