import base64, glob, json, os, random, re, string, time, xbmc

from collections import OrderedDict
from resources.lib.base.l1.constants import ADDON_ID, ADDON_PROFILE
from resources.lib.base.l2 import settings
from resources.lib.base.l2.log import log
from resources.lib.base.l3.language import _
from resources.lib.base.l3.util import check_key, get_credentials, encode32, is_file_older_than_x_days, is_file_older_than_x_minutes, load_file, load_profile, load_prefs, save_profile, save_prefs, set_credentials, write_file
from resources.lib.base.l4.exceptions import Error
from resources.lib.base.l4.session import Session
from resources.lib.base.l5.api import api_download, api_get_channels
from resources.lib.constants import CONST_BASE_HEADERS, CONST_URLS, CONST_IMAGES
from resources.lib.util import plugin_process_info
from urllib.parse import parse_qs, urlparse, quote_plus
from xml.sax.saxutils import escape

def _tmobile_headers(csrf_token=''):
    headers = {
        'Accept': '*/*',
        'Accept-Encoding': 'gzip, deflate',
        'Accept-Language': 'en-US,en;q=0.9,nl;q=0.8',
        'Cache-Control': 'no-cache',
        'Content-Type': 'application/json',
        'DNT': '1',
        'Origin': 'https://tv.odido.nl',
        'Pragma': 'no-cache',
        'Referer': 'https://tv.odido.nl/',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
    }

    if csrf_token:
        headers['X_CSRFToken'] = csrf_token

    return headers

#Included from base.l7.plugin
#api_clean_after_playback
#api_get_info

#Included from base.l8.menu
#api_add_to_watchlist
#api_get_profiles
#api_list_watchlist
#api_login
#api_play_url
#api_remove_from_watchlist
#api_search
#api_set_profile
#api_vod_download
#api_vod_season
#api_vod_seasons
#api_watchlist_listing

def api_add_to_watchlist(id, series='', season='', program_type='', type='watchlist'):
    return None

def api_clean_after_playback(stoptime):
    pass

def api_getCookies(cookie_jar, domain):
    cookie_dict = json.loads(cookie_jar)
    found = ['%s=%s' % (name, value) for (name, value) in cookie_dict.items()]
    return '; '.join(found)

def api_get_info(id, channel=''):
    profile_settings = load_profile(profile_id=1)

    info = {}
    headers = {'Content-Type': 'application/json', 'X_CSRFToken': profile_settings['csrf_token']}
    militime = int(time.time() * 1000)

    data = api_get_channels()

    session_post_data = {
        'needChannel': '0',
        'queryChannel': {
            'channelIDs': [
                id,
            ],
            'isReturnAllMedia': '1',
        },
        'queryPlaybill': {
            'count': '1',
            'endTime': militime,
            'isFillProgram': '1',
            'offset': '0',
            'startTime': militime,
            'type': '0',
        }
    }

    channel_url = '{base_url}/VSP/V3/QueryPlaybillListStcProps?SID=queryPlaybillListStcProps3&DEVICE=PC&DID={deviceID}&from=throughMSAAccess'.format(base_url=CONST_URLS['base'], deviceID=profile_settings['devicekey'])

    download = api_download(url=channel_url, type='post', headers=headers, data=session_post_data, json_data=True, return_json=True)
    data = download['data']
    code = download['code']

    if not code or not code == 200 or not data or not check_key(data, 'result') or not check_key(data['result'], 'retCode') or not data['result']['retCode'] == '000000000' or not check_key(data, 'channelPlaybills') or not check_key(data['channelPlaybills'][0], 'playbillLites') or not check_key(data['channelPlaybills'][0]['playbillLites'][0], 'ID'):
        return info

    id = data['channelPlaybills'][0]['playbillLites'][0]['ID']

    session_post_data = {
        'playbillID': id,
        'channelNamespace': '310303',
        'isReturnAllMedia': '1',
    }

    program_url = '{base_url}/VSP/V3/QueryPlaybill?from=throughMSAAccess'.format(base_url=CONST_URLS['base'])

    download = api_download(url=program_url, type='post', headers=headers, data=session_post_data, json_data=True, return_json=True)
    data = download['data']
    code = download['code']

    if not code or not code == 200 or not data or not check_key(data, 'result') or not check_key(data['result'], 'retCode') or not data['result']['retCode'] == '000000000' or not check_key(data, 'playbillDetail'):
        return info
    else:
        info = data['playbillDetail']

    info = plugin_process_info({'title': '', 'channel': channel, 'info': info})

    return info

def api_get_session(force=0, return_data=False):
    force = int(force)
    profile_settings = load_profile(profile_id=1)

    heartbeat_url = '{base_url}/VSP/V3/OnLineHeartbeat?from=inMSAAccess'.format(base_url=CONST_URLS['base'])

    headers = {'Content-Type': 'application/json', 'X_CSRFToken': profile_settings['csrf_token']}

    session_post_data = {}

    download = api_download(url=heartbeat_url, type='post', headers=headers, data=session_post_data, json_data=True, return_json=True)
    data = download['data']
    code = download['code']

    if not code or not code == 200 or not data or not check_key(data, 'result') or not check_key(data['result'], 'retCode') or not data['result']['retCode'] == '000000000':
        login_result = api_login()

        if not login_result['result']:
            if return_data == True:
                return {'result': False, 'data': login_result['data'], 'code': login_result['code']}

            return False

    profile_settings = load_profile(profile_id=1)
    profile_settings['last_login_success'] = 1
    profile_settings['last_login_time'] = int(time.time())
    save_profile(profile_id=1, profile=profile_settings)

    if return_data == True:
        return {'result': True, 'data': data, 'code': code}

    return True

def api_get_profiles():
    return None

def api_list_watchlist(type='watchlist'):
    return None

def api_login():
    creds = get_credentials()
    username = creds['username']
    password = creds['password']

    try:
        os.remove(os.path.join(ADDON_PROFILE, 'stream_cookies'))
    except:
        pass

    profile_settings = load_profile(profile_id=1)
    profile_settings['csrf_token'] = ''
    profile_settings['user_filter'] = ''

    if not profile_settings or not check_key(profile_settings, 'devicekey') or len(profile_settings['devicekey']) == 0:
        devicekey = ''.join(random.choice(string.digits) for _ in range(10))
        profile_settings['devicekey'] = devicekey

    save_profile(profile_id=1, profile=profile_settings)

    login_url = '{base_url}/VSP/V3/Authenticate?from=throughMSAAccess'.format(base_url=CONST_URLS['base'])

    session_post_data = {
        "authenticateBasic": {
            'VUID': '6_7_{devicekey}'.format(devicekey=profile_settings['devicekey']),
            'clientPasswd': password,
            'isSupportWebpImgFormat': '0',
            'lang': 'nl',
            'needPosterTypes': [
                '1',
                '2',
                '3',
                '4',
                '5',
                '6',
                '7',
            ],
            'timeZone': 'Europe/Amsterdam',
            'userID': username,
            'userType': '0',
        },
        'authenticateDevice': {
            'CADeviceInfos': [
                {
                    'CADeviceID': profile_settings['devicekey'],
                    'CADeviceType': '7',
                },
            ],
            'deviceModel': '3103_PCClient',
            'physicalDeviceID': profile_settings['devicekey'],
            'terminalID': profile_settings['devicekey'],
        },
        'authenticateTolerant': {
            'areaCode': '',
            'bossID': '',
            'subnetID': '',
            'templateName': '',
            'userGroup': '',
        },
    }

    download = api_download(url=login_url, type='post', headers=None, data=session_post_data, json_data=True, return_json=True)
    data = download['data']
    code = download['code']

    if not code or not code == 200 or not data or not check_key(data, 'result') or not check_key(data['result'], 'retCode') or not data['result']['retCode'] == '000000000' or not check_key(data, 'csrfToken'):
        if check_key(data, 'result') and check_key(data['result'], 'retCode') and data['result']['retCode'] == "157022007" and check_key(data, 'devices'):
            for row in data['devices']:
                if not check_key(row, 'name') and check_key(row, 'deviceModel') and check_key(row, 'status') and check_key(row, 'onlineState') and check_key(row, 'physicalDeviceID') and row['deviceModel'] == '3103_PCClient' and row['status'] == '1' and row['onlineState'] == '0':
                    profile_settings['devicekey'] = row['physicalDeviceID']
                    save_profile(profile_id=1, profile=profile_settings)

                    return api_login()

            for row in data['devices']:
                if check_key(row, 'status') and check_key(row, 'onlineState') and check_key(row, 'physicalDeviceID'):
                    if row['status'] == '1' and row['onlineState'] == '0' and (not check_key(row, 'name') or len(str(row['name'])) < 1 or 'PC' in str(row['name'])):
                        profile_settings['devicekey'] = row['physicalDeviceID']
                        save_profile(profile_id=1, profile=profile_settings)

                        return api_login()

            for row in data['devices']:
                if check_key(row, 'status') and check_key(row, 'onlineState') and check_key(row, 'physicalDeviceID'):
                    if row['status'] == '1':
                        profile_settings['devicekey'] = row['physicalDeviceID']
                        save_profile(profile_id=1, profile=profile_settings)

                        return api_login()

        return { 'code': code, 'data': data, 'result': False }

    profile_settings['csrf_token'] = data['csrfToken']
    profile_settings['user_filter'] = data['userFilter']
    save_profile(profile_id=1, profile=profile_settings)

    return { 'code': code, 'data': data, 'result': True }

def api_play_url(type, channel=None, id=None, video_data=None, from_beginning=0, pvr=0, change_audio=0):
    playdata = {'path': '', 'license': '', 'info': '', 'properties': {}}
    license = ''

    if not api_get_session():
        return playdata

    from_beginning = int(from_beginning)
    pvr = int(pvr)
    change_audio = int(change_audio)

    profile_settings = load_profile(profile_id=1)

    headers = {'Content-Type': 'application/json', 'X_CSRFToken': profile_settings['csrf_token']}

    mediaID = None
    info = {}
    properties = {}

    if not type or not len(str(type)) > 0:
        return playdata

    militime = int(time.time() * 1000)

    if not type == 'vod':
        if video_data:
            try:
                video_data = json.loads(video_data)
                mediaID = int(video_data['media_id']) + 1
            except:
                pass

        data = api_get_channels()

        try:
            mediaID = data[str(channel)]['assetid']
        except:
            pass

    if type == 'channel' and channel:
        if not pvr == 1 or settings.getBool(key='ask_start_from_beginning') or from_beginning == 1:
            session_post_data = {
                'needChannel': '0',
                'queryChannel': {
                    'channelIDs': [
                        channel,
                    ],
                    'isReturnAllMedia': '1',
                },
                'queryPlaybill': {
                    'count': '1',
                    'endTime': militime,
                    'isFillProgram': '1',
                    'offset': '0',
                    'startTime': militime,
                    'type': '0',
                }
            }

            channel_url = '{base_url}/VSP/V3/QueryPlaybillListStcProps?SID=queryPlaybillListStcProps3&DEVICE=PC&DID={deviceID}&from=throughMSAAccess'.format(base_url=CONST_URLS['base'], deviceID=profile_settings['devicekey'])

            download = api_download(url=channel_url, type='post', headers=headers, data=session_post_data, json_data=True, return_json=True)
            data = download['data']
            code = download['code']

            if not code or not code == 200 or not data or not check_key(data, 'result') or not check_key(data['result'], 'retCode') or not data['result']['retCode'] == '000000000' or not check_key(data, 'channelPlaybills') or not check_key(data['channelPlaybills'][0], 'playbillLites') or not check_key(data['channelPlaybills'][0]['playbillLites'][0], 'ID'):
                return playdata

            id = data['channelPlaybills'][0]['playbillLites'][0]['ID']

            session_post_data = {
                'playbillID': id,
                'channelNamespace': '310303',
                'isReturnAllMedia': '1',
            }

            program_url = '{base_url}/VSP/V3/QueryPlaybill?from=throughMSAAccess'.format(base_url=CONST_URLS['base'])

            download = api_download(url=program_url, type='post', headers=headers, data=session_post_data, json_data=True, return_json=True)
            data = download['data']
            code = download['code']

            if not code or not code == 200 or not data or not check_key(data, 'result') or not check_key(data['result'], 'retCode') or not data['result']['retCode'] == '000000000' or not check_key(data, 'playbillDetail'):
                info = {}
            else:
                info = data['playbillDetail']

        session_post_data = {
            "businessType": "BTV",
            "channelID": channel,
            "checkLock": {
                "checkType": "0",
            },
            "isHTTPS": "1",
            "isReturnProduct": "1",
            "mediaID": mediaID,
        }
    elif type == 'program' and id:
        if not pvr == 1:
            session_post_data = {
                'playbillID': id,
                'channelNamespace': '310303',
                'isReturnAllMedia': '1',
            }

            program_url = '{base_url}/VSP/V3/QueryPlaybill?from=throughMSAAccess'.format(base_url=CONST_URLS['base'])

            download = api_download(url=program_url, type='post', headers=headers, data=session_post_data, json_data=True, return_json=True)
            data = download['data']
            code = download['code']

            if not code or not code == 200 or not data or not check_key(data, 'result') or not check_key(data['result'], 'retCode') or not data['result']['retCode'] == '000000000' or not check_key(data, 'playbillDetail'):
                info = {}
            else:
                info = data['playbillDetail']

        session_post_data = {
            "businessType": "CUTV",
            "channelID": channel,
            "checkLock": {
                "checkType": "0",
            },
            "isHTTPS": "1",
            "isReturnProduct": "1",
            "mediaID": mediaID,
            "playbillID": id,
        }
    elif type == 'vod' and id:
        session_post_data = {
            'VODID': id
        }

        program_url = '{base_url}/VSP/V3/QueryVOD?from=throughMSAAccess'.format(base_url=CONST_URLS['base'])

        download = api_download(url=program_url, type='post', headers=headers, data=session_post_data, json_data=True, return_json=True)
        data = download['data']
        code = download['code']

        if not code or not code == 200 or not data or not check_key(data, 'result') or not check_key(data['result'], 'retCode') or not data['result']['retCode'] == '000000000' or not check_key(data, 'VODDetail') or not check_key(data['VODDetail'], 'VODType'):
            return playdata

        info = data['VODDetail']

        session_post_data = {
            "VODID": id,
            "checkLock": {
                "checkType": "0",
            },
            "isHTTPS": "1",
            "isReturnProduct": "1",
            "mediaID": '',
        }

        if not check_key(info, 'mediaFiles') or not check_key(info['mediaFiles'][0], 'ID'):
            return playdata

        if check_key(info, 'series') and check_key(info['series'][0], 'VODID'):
            session_post_data["seriesID"] = info['series'][0]['VODID']

        session_post_data["mediaID"] = info['mediaFiles'][0]['ID']

    if not len(str(session_post_data["mediaID"])) > 0:
        return playdata

    if type == 'vod':
        play_url_path = '{base_url}/VSP/V3/PlayVOD?from=throughMSAAccess'.format(base_url=CONST_URLS['base'])
    else:
        play_url_path = '{base_url}/VSP/V3/PlayChannel?from=throughMSAAccess'.format(base_url=CONST_URLS['base'])

    download = api_download(url=play_url_path, type='post', headers=headers, data=session_post_data, json_data=True, return_json=True)
    data = download['data']
    code = download['code']

    try:
        write_file(file='playchannel_response.json', data=data, isJSON=True)
        write_file(file='playchannel_response_url', data=download['url'], isJSON=False)
        write_file(file='playchannel_response_headers.json', data=dict(download['headers']), isJSON=True)
    except:
        pass

    if not code or not code == 200 or not data or not check_key(data, 'result') or not check_key(data['result'], 'retCode') or not data['result']['retCode'] == '000000000' or not check_key(data, 'playURL'):
        return playdata

    path = data['playURL']

    if check_key(data, 'authorizeResult'):
        profile_settings = load_profile(profile_id=1)

        data['authorizeResult']['cookie'] = api_getCookies(load_file('stream_cookies'), '')
        license = data['authorizeResult']

    mpd = ''

    if change_audio == 1:
        download = api_download(url=path, type='get', headers=headers, data=None, json_data=False, return_json=False)
        data = download['data']
        code = download['code']

        if code and code == 200:
            mpd = data

    playdata = {'path': path, 'mpd': mpd, 'license': license, 'info': info, 'properties': properties}

    return playdata

def api_remove_from_watchlist(id, type='watchlist'):
    return None

def api_search(query):
    return None

def api_set_profile(id=''):
    return None

def api_vod_download():
    return None

def api_vod_season(series, id, use_cache=True):
    if not api_get_session():
        return None

    type = "vod_season_{id}".format(id=id)
    type = encode32(type)

    file = os.path.join("cache", "{type}.json".format(type=type))
    cache = 0

    if not is_file_older_than_x_days(file=os.path.join(ADDON_PROFILE, file), days=0.5) and use_cache == True:
        data = load_file(file=file, isJSON=True)
        cache = 1
    else:
        profile_settings = load_profile(profile_id=1)

        headers = {'Content-Type': 'application/json', 'X_CSRFToken': profile_settings['csrf_token']}

        session_post_data = {
            'VODID': str(id),
            'offset': '0',
            'count': '35',
        }

        seasons_url = '{base_url}/VSP/V3/QueryEpisodeList?from=throughMSAAccess'.format(base_url=CONST_URLS['base'])

        download = api_download(url=seasons_url, type='post', headers=headers, data=session_post_data, json_data=True, return_json=True)
        data = download['data']
        code = download['code']

        if code and code == 200 and data and check_key(data, 'result') and check_key(data['result'], 'retCode') and data['result']['retCode'] == '000000000' and check_key(data, 'episodes'):
            write_file(file=file, data=data, isJSON=True)

    return {'data': data, 'cache': cache}

def api_vod_seasons(type, id, use_cache=True):
    if not api_get_session():
        return None

    type = "vod_seasons_{id}".format(id=id)
    type = encode32(type)

    file = os.path.join("cache", "{type}.json".format(type=type))
    cache = 0

    if not is_file_older_than_x_days(file=os.path.join(ADDON_PROFILE, file), days=0.5) and use_cache == True:
        data = load_file(file=file, isJSON=True)
        cache = 1
    else:
        profile_settings = load_profile(profile_id=1)

        headers = {'Content-Type': 'application/json', 'X_CSRFToken': profile_settings['csrf_token']}

        session_post_data = {
            'VODID': str(id),
            'offset': '0',
            'count': '50',
        }

        seasons_url = '{base_url}/VSP/V3/QueryEpisodeList?from=throughMSAAccess'.format(base_url=CONST_URLS['base'])

        download = api_download(url=seasons_url, type='post', headers=headers, data=session_post_data, json_data=True, return_json=True)
        data = download['data']
        code = download['code']

        if code and code == 200 and data and check_key(data, 'result') and check_key(data['result'], 'retCode') and data['result']['retCode'] == '000000000' and check_key(data, 'episodes'):
            write_file(file=file, data=data, isJSON=True)

    return {'data': data, 'cache': cache}

def _tmobile_chunked(values, size):
    for idx in range(0, len(values), size):
        yield values[idx:idx + size]

def _tmobile_format_xmltv_timestamp(epoch_ms):
    return time.strftime('%Y%m%d%H%M%S +0000', time.gmtime(int(epoch_ms) // 1000))

def _tmobile_programme_to_xml(programme):
    if not check_key(programme, 'ID') or not check_key(programme, 'channelID') or not check_key(programme, 'startTime') or not check_key(programme, 'endTime') or not check_key(programme, 'name'):
        return ''

    attrs = [
        'start="{start}"'.format(start=_tmobile_format_xmltv_timestamp(programme['startTime'])),
        'stop="{stop}"'.format(stop=_tmobile_format_xmltv_timestamp(programme['endTime'])),
        'channel="{channel}"'.format(channel=escape(str(programme['channelID']))),
    ]

    if check_key(programme, 'ID') and ((check_key(programme, 'isCUTV') and str(programme['isCUTV']) == '1') or (check_key(programme, 'CUTVStatus') and str(programme['CUTVStatus']) == '1')):
        attrs.append('catchup-id="{catchup_id}"'.format(catchup_id=escape(str(programme['ID']))))

    lines = ['<programme {attrs}>'.format(attrs=' '.join(attrs))]
    lines.append('<title lang="nl">{}</title>'.format(escape(str(programme['name']))))

    subtitle = ''

    if check_key(programme, 'playbillSeries') and check_key(programme['playbillSeries'], 'sitcomName'):
        subtitle = str(programme['playbillSeries']['sitcomName']).strip()

    if subtitle:
        lines.append('<sub-title lang="nl">{}</sub-title>'.format(escape(subtitle)))
        lines.append('<desc lang="nl">{}</desc>'.format(escape(subtitle)))

    genres = []

    if check_key(programme, 'genres'):
        for genre in programme['genres']:
            if check_key(genre, 'genreName'):
                genres.append(str(genre['genreName']))

    for genre in genres:
        lines.append('<category lang="nl">{}</category>'.format(escape(genre)))

    if check_key(programme, 'picture') and check_key(programme['picture'], 'posters') and len(programme['picture']['posters']) > 0:
        lines.append('<icon src="{}"></icon>'.format(escape(str(programme['picture']['posters'][0]))))

    lines.append('</programme>')

    return ''.join(lines)

def _tmobile_fetch_playbill_window(session, profile, channel_ids, start_time, end_time, count='128'):
    url = 'https://tv.odido.nl/VSP/V3/QueryPlaybillListStcProps?SID=queryPlaybillListStcProps3&DEVICE=PC&DID={devicekey}&from=throughMSAAccess'.format(devicekey=profile['devicekey'])
    payload = {
        'needChannel': '0',
        'queryChannel': {
            'channelIDs': channel_ids,
            'isReturnAllMedia': '1',
        },
        'queryPlaybill': {
            'count': str(count),
            'endTime': int(end_time),
            'isFillProgram': '1',
            'offset': '0',
            'startTime': int(start_time),
            'type': '0',
        }
    }

    response = session.post(url, json=payload, timeout=30)

    try:
        data = response.json()
    except:
        return None

    if response.status_code != 200 or not data or not check_key(data, 'result') or not check_key(data['result'], 'retCode') or data['result']['retCode'] != '000000000':
        return None

    return data

def _tmobile_get_live_epg():
    channels = api_get_channels()

    if not channels:
        return None

    if not api_get_session():
        return None

    profile = load_profile(profile_id=1)

    if not profile or not check_key(profile, 'devicekey') or not check_key(profile, 'csrf_token'):
        return None

    session = Session(headers=_tmobile_headers(profile['csrf_token']), cookies_key='cookies')

    try:
        programmes_by_channel = {}
        now = int(time.time())
        windows = []

        for day_offset in range(-7, 2):
            start_time = (now + (day_offset * 86400)) * 1000
            end_time = start_time + (86400 * 1000)
            windows.append((start_time, end_time))

        for channel_chunk in _tmobile_chunked(list(channels.keys()), 20):
            for start_time, end_time in windows:
                data = _tmobile_fetch_playbill_window(session, profile, channel_chunk, start_time, end_time)

                if not data or not check_key(data, 'channelPlaybills'):
                    continue

                for row in data['channelPlaybills']:
                    if not check_key(row, 'playbillLites'):
                        continue

                    for programme in row['playbillLites']:
                        if not check_key(programme, 'channelID') or not check_key(programme, 'ID'):
                            continue

                        channel_id = str(programme['channelID'])

                        if channel_id not in programmes_by_channel:
                            programmes_by_channel[channel_id] = OrderedDict()

                        programmes_by_channel[channel_id][str(programme['ID'])] = programme

        return programmes_by_channel
    finally:
        try:
            session.close()
        except:
            pass

def _tmobile_write_epg_cache(programmes_by_channel):
    cache_dir = os.path.join(ADDON_PROFILE, 'cache', 'tmobile')

    if not os.path.isdir(cache_dir):
        os.makedirs(cache_dir)

    for stale_file in glob.glob(os.path.join(cache_dir, '*.xml')):
        try:
            os.remove(stale_file)
        except:
            pass

    written = 0

    for channel_id, programmes in programmes_by_channel.items():
        xml = []

        for _, programme in sorted(programmes.items(), key=lambda item: int(item[1].get('startTime', 0))):
            item_xml = _tmobile_programme_to_xml(programme)

            if item_xml:
                xml.append(item_xml)

        if not xml:
            continue

        file_name = base64.b32encode(channel_id.encode('utf-8')).decode('utf-8') + '.xml'
        write_file(file=os.path.join('cache', 'tmobile', file_name), data=''.join(xml), isJSON=False)
        written += 1

    write_file(file=os.path.join('tmp', 't.epg.timestamp'), data=str(int(time.time())), isJSON=False)

    return written > 0

def api_get_all_epg():
    programmes_by_channel = _tmobile_get_live_epg()

    if not programmes_by_channel:
        return False

    return _tmobile_write_epg_cache(programmes_by_channel)

def api_vod_subscription():
    return None

def api_watchlist_listing():
    return None
