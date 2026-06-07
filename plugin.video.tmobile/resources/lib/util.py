import _strptime
import certifi, datetime, glob, os, re, requests, sys, xbmc
from xml.sax.saxutils import escape

from collections import OrderedDict
from resources.lib.base.l1.constants import ADDON_ID, ADDON_PROFILE, DEFAULT_USER_AGENT, PROVIDER_NAME
from resources.lib.base.l2 import settings
from resources.lib.base.l2.log import log
from resources.lib.base.l3.language import _
from resources.lib.base.l3.util import check_key, convert_datetime_timezone, date_to_nl_dag, date_to_nl_maand, encode32, encode_obj, load_channels, load_file, load_order, load_prefs, load_profile, load_radio_order, load_radio_prefs, write_file
from resources.lib.base.l4 import gui
from resources.lib.base.l5.api import api_get_channels
from resources.lib.base.l6 import inputstream
from resources.lib.constants import CONST_IMAGES
from urllib.parse import urlencode

#Included from base.l7.plugin
#plugin_get_device_id

#Included from base.l8.menu
#plugin_ask_for_creds
#plugin_check_devices
#plugin_check_first
#plugin_login_error
#plugin_post_login
#plugin_process_info
#plugin_process_playdata
#plugin_process_vod
#plugin_process_vod_season
#plugin_process_vod_seasons
#plugin_process_watchlist
#plugin_process_watchlist_listing
#plugin_renew_token
#plugin_vod_subscription_filter

def plugin_ask_for_creds(creds):
    username = str(gui.input(message=_.ASK_USERNAME, default=creds['username'])).strip()

    if not len(str(username)) > 0:
        gui.ok(message=_.EMPTY_USER, heading=_.LOGIN_ERROR_TITLE)
        return {'result': False, 'username': '', 'password': ''}

    password = str(gui.input(message=_.ASK_PASSWORD, hide_input=True)).strip()

    if not len(str(password)) > 0:
        gui.ok(message=_.EMPTY_PASS, heading=_.LOGIN_ERROR_TITLE)
        return {'result': False, 'username': '', 'password': ''}

    return {'result': True, 'username': username, 'password': password}

def plugin_check_devices():
    pass

def plugin_check_first():
    try:
        requests.get('https://tv.odido.nl')
    except requests.exceptions.SSLError as err:
        customca = requests.get('https://cacerts.digicert.com/DigiCertTLSRSASHA2562020CA1-1.crt.pem').content
        cafile = certifi.where()
        with open(cafile, 'ab') as outfile:
            outfile.write(b'\n')
            outfile.write(customca)

def plugin_get_device_id():
    return 'NOTNEEDED'

def plugin_login_error(login_result):
    if check_key(login_result['data'], 'result') and check_key(login_result['data']['result'], 'retCode') and login_result['data']['result']['retCode'] == "157022007":
        gui.ok(message=_.TOO_MANY_DEVICES, heading=_.LOGIN_ERROR_TITLE)
    else:
        gui.ok(message=_.LOGIN_ERROR, heading=_.LOGIN_ERROR_TITLE)

def plugin_post_login():
    pass

def plugin_process_info(playdata):
    info = {
        'label1': '',
        'label2': '',
        'description': '',
        'image': '',
        'image_large': '',
        'duration': 0,
        'credits': [],
        'cast': [],
        'director': [],
        'writer': [],
        'genres': [],
        'year': '',
    }

    if check_key(playdata['info'], 'startTime') and check_key(playdata['info'], 'endTime'):
        startT = datetime.datetime.fromtimestamp(int(int(playdata['info']['startTime']) // 1000))
        startT = convert_datetime_timezone(startT, "UTC", "UTC")
        endT = datetime.datetime.fromtimestamp(int(int(playdata['info']['endTime']) // 1000))
        endT = convert_datetime_timezone(endT, "UTC", "UTC")

        write_file(file='stream_start', data=int(int(playdata['info']['startTime']) // 1000), isJSON=False)
        write_file(file='stream_end', data=int(int(playdata['info']['endTime']) // 1000), isJSON=False)

        info['duration'] = int((endT - startT).total_seconds())

        if xbmc.getLanguage(xbmc.ISO_639_1) == 'nl':
            info['label1'] = '{weekday} {day} {month} {yearhourminute} '.format(weekday=date_to_nl_dag(startT), day=startT.strftime("%d"), month=date_to_nl_maand(startT), yearhourminute=startT.strftime("%Y %H:%M"))
        else:
            info['label1'] = startT.strftime("%A %d %B %Y %H:%M ").capitalize()

        info['label1'] += " - "

    if check_key(playdata['info'], 'name'):
        info['label1'] += playdata['info']['name']
        info['label2'] = playdata['info']['name']

    if check_key(playdata['info'], 'introduce'):
        info['description'] = playdata['info']['introduce']

    if check_key(playdata['info'], 'picture'):
        info['image'] = playdata['info']['picture']['posters'][0]
        info['image_large'] = playdata['info']['picture']['posters'][0]

    data = api_get_channels()

    try:
        info['label2'] += " - "  + data[str(playdata['channel'])]['name']
    except:
        pass

    return info

def plugin_process_playdata(playdata):
    profile_settings = load_profile(profile_id=1)

    license_headers = {
        'User-Agent': DEFAULT_USER_AGENT,
        'X_CSRFToken': profile_settings['csrf_token'],
        'Cookie': playdata['license']['cookie'],
    }
    manifest_headers = {
        'User-Agent': DEFAULT_USER_AGENT,
    }
    stream_headers = {
        'User-Agent': DEFAULT_USER_AGENT,
    }

    if check_key(playdata, 'license') and check_key(playdata['license'], 'triggers') and check_key(playdata['license']['triggers'][0], 'licenseURL'):
        item_inputstream = inputstream.Widevine(
            #license_key = playdata['license']['triggers'][0]['licenseURL'],
            #manifest_update_parameter = 'update',
            license_key = "http://127.0.0.1:11189/{provider}/license".format(provider=PROVIDER_NAME),
            manifest_headers = manifest_headers,
            stream_headers = stream_headers,
            license_headers = license_headers,
        )
        
        write_file(file='stream_license', data=playdata['license']['triggers'][0]['licenseURL'], isJSON=False)

        if check_key(playdata['license']['triggers'][0], 'customData'):
            license_headers['AcquireLicense.CustomData'] = playdata['license']['triggers'][0]['customData']
            license_headers['CADeviceType'] = 'Widevine OTT client'
    else:
        item_inputstream = inputstream.MPD(
            #manifest_update_parameter = 'update',
        )
        license_headers = stream_headers

    return item_inputstream, license_headers

def plugin_process_vod(data, start=0):
    items = {}

    return data

def plugin_process_vod_season(series, id, data):
    season = []

    if not data or not check_key(data, 'episodes'):
        return None

    for row in data['episodes']:
        if check_key(row, 'VOD') and check_key(row['VOD'], 'ID') and check_key(row['VOD'], 'name') and check_key(row, 'sitcomNO'):
            image = ''
            duration = 0

            if not check_key(row['VOD'], 'mediaFiles') or not check_key(row['VOD']['mediaFiles'][0], 'ID'):
                continue

            if check_key(row['VOD']['mediaFiles'][0], 'elapseTime'):
                duration = row['VOD']['mediaFiles'][0]['elapseTime']

            if check_key(row['VOD'], 'picture') and check_key(row['VOD']['picture'], 'posters'):
                image = row['VOD']['picture']['posters'][0]

            label = '{episode} - {title}'.format(episode=row['sitcomNO'], title=row['VOD']['name'])

            season.append({'label': label, 'id': row['VOD']['ID'], 'media_id': row['VOD']['mediaFiles'][0]['ID'], 'duration': duration, 'title': row['VOD']['name'], 'episodeNumber': row['sitcomNO'], 'description': '', 'image': image})

    return season

def plugin_process_vod_seasons(id, data):
    seasons = []

    if not data or not check_key(data, 'episodes'):
        return None

    for row in data['episodes']:
        if check_key(row, 'VOD') and check_key(row['VOD'], 'ID') and check_key(row, 'sitcomNO'):
            image = ''

            if check_key(row['VOD'], 'picture') and check_key(row['VOD']['picture'], 'posters'):
                image = row['VOD']['picture']['posters'][0]

            seasons.append({'id': row['VOD']['ID'], 'seriesNumber': row['sitcomNO'], 'description': '', 'image': image})

    return {'type': 'seasons', 'seasons': seasons}

def plugin_process_watchlist(data, type='watchlist'):
    items = {}

    return items

def plugin_process_watchlist_listing(data, id=None, type='watchlist'):
    items = {}

    return items

def plugin_renew_token(data):
    return None
    
def plugin_vod_subscription_filter():
    return None

def create_epg():
    prefs = load_prefs(profile_id=1)
    channels = load_file(file=os.path.join('cache', 'channels.json'), ext=False, isJSON=True)
    cache_dir = os.path.join(ADDON_PROFILE, 'cache', 'tmobile')
    xml_files = glob.glob(os.path.join(cache_dir, '*.xml'))

    if not xml_files or not channels or not prefs:
        return False

    new_xml_start = '<?xml version="1.0" encoding="utf-8" ?><tv generator-info-name="{addonid}">'.format(addonid=ADDON_ID)
    new_xml_end = '</tv>'
    new_xml_channels = ''
    new_xml_epg = ''
    wrote_any = False

    for channel_id, channel in channels.items():
        try:
            row = prefs.get(str(channel_id), prefs.get(channel_id))

            if not row or not check_key(row, 'live') or not int(row['live']) == 1:
                continue

            channel_id = str(channel_id)
            data = load_file(os.path.join('cache', 'tmobile', encode32(channel_id) + '.xml'), ext=False, isJSON=False)

            if data:
                new_xml_epg += data

                try:
                    new_xml_channels += '<channel id="{channelid}"><display-name>{channelname}</display-name><icon src="{channelicon}"></icon><desc></desc></channel>'.format(
                        channelid=escape(channel_id),
                        channelname=escape(str(channel.get('name', ''))),
                        channelicon=escape(str(channel.get('icon', ''))),
                    )
                except:
                    pass

                wrote_any = True
        except:
            pass

    if not wrote_any:
        return False

    write_file(file='epg.xml', data=new_xml_start + new_xml_channels + new_xml_epg + new_xml_end, isJSON=False)
    return True

def create_playlist():
    channels = load_file(file=os.path.join('cache', 'channels.json'), ext=False, isJSON=True)
    prefs = load_prefs(profile_id=1)
    playlist = u'#EXTM3U\n'
    wrote_any = False

    if not channels or not prefs:
        return False

    for channel_id, row in channels.items():
        try:
            pref = prefs.get(str(channel_id), prefs.get(channel_id))

            if not pref or not check_key(pref, 'live') or not int(pref['live']) == 1:
                continue

            channel_id = str(channel_id)
            image = str(row.get('icon', '')) if check_key(row, 'icon') else ''
            channel_no = str(row.get('channelno', ''))
            channel_name = str(row.get('name', ''))
            group = 'TV'
            path = str('plugin://{addonid}/?_=play_video&type=channel&channel={channel}&id={asset}&_is_live=True'.format(
                addonid=ADDON_ID,
                channel=channel_id,
                asset=str(row.get('assetid', '')),
            ))

            replay = int(pref['replay']) if check_key(pref, 'replay') else 0

            try:
                if replay == 1:
                    catchup = str(
                        'plugin://{addonid}/?_=play_video&type=program&channel={channel}&id={{catchup-id}}&pvr=1&_l=.pvr'.format(
                            addonid=ADDON_ID,
                            channel=channel_id,
                        )
                    )
                    playlist += u'#EXTINF:0 tvg-id="{id}" tvg-chno="{channel}" tvg-name="{name}" tvg-logo="{logo}" catchup="default" catchup-source="{catchup}" catchup-days="7" group-title="{group}" radio="false",{name}\n{path}\n'.format(id=channel_id, channel=channel_no, name=channel_name, logo=image, catchup=catchup, group=group, path=path)
                else:
                    playlist += u'#EXTINF:0 tvg-id="{id}" tvg-chno="{channel}" tvg-name="{name}" tvg-logo="{logo}" group-title="{group}" radio="false",{name}\n{path}\n'.format(id=channel_id, channel=channel_no, name=channel_name, logo=image, group=group, path=path)
                wrote_any = True
            except:
                pass
        except:
            pass

    profile_settings = load_profile(profile_id=1)

    if check_key(profile_settings, 'radio') and int(profile_settings['radio']) == 1:
        order = load_radio_order(profile_id=1)
        prefs = load_radio_prefs(profile_id=1)
        radio = load_channels(type='radio')

        for currow in order:
            try:
                ch_no = str(order[currow])
                row = prefs[str(currow)]

                if not check_key(row, 'radio') or int(row['radio']) == 0:
                    continue

                id = str(currow)

                if len(id) > 0:
                    if not radio or not check_key(radio, id) or not check_key(radio[id], 'name') or not check_key(radio[id], 'url'):
                        continue

                    if check_key(radio[id], 'mod_name') and len(str(radio[id]['mod_name'])) > 0:
                        label = radio[id]['mod_name']
                    else:
                        label = radio[id]['name']

                    path = radio[id]['url']

                    if check_key(radio[id], 'icon') and len(str(radio[id]['icon'])) > 0:
                        image = radio[id]['icon']
                    else:
                        image = ''

                    if not check_key(row, 'group') or len(str(row['group'])) == 0:
                        group = 'Radio'
                    else:
                        group = row['group']

                    playlist += u'#EXTINF:0 tvg-id="{id}" tvg-chno="{channel}" tvg-name="{name}" tvg-logo="{logo}" group-title="{group}" radio="true",{name}\n{path}\n'.format(id=id, channel=ch_no, name=label, logo=image, group=group, path=path)
                    wrote_any = True
            except:
                pass

    if not wrote_any:
        return False

    write_file(file='playlist.m3u8', data=playlist, isJSON=False)
    return True
