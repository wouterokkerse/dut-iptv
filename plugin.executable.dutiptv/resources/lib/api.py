import base64, glob, json, os, requests, time, xbmc

from collections import OrderedDict
from resources.lib.base.l1.constants import ADDON_ID, ADDON_PROFILE, CONST_DUT_EPG_BASE, SESSION_CHUNKSIZE
from resources.lib.base.l1.encrypt import Credentials
from resources.lib.base.l2.log import log
from resources.lib.base.l3.util import check_key, fixBadZipfile, is_file_older_than_x_days, load_file, load_profile, write_file
from resources.lib.util import clear_cache_connector
from xml.sax.saxutils import escape

#Included from base.l7.plugin
#api_clean_after_playback
#api_get_info

def api_clean_after_playback(stoptime):
    pass

def api_get_channels():
    directory = os.path.dirname(os.path.join(ADDON_PROFILE, 'tmp', 'a.channels.zip'))

    if not os.path.exists(directory):
        os.makedirs(directory)

    directory = os.path.dirname(os.path.join(ADDON_PROFILE, "cache", "a.channels.json"))

    if not os.path.exists(directory):
        os.makedirs(directory)

    channels_url = '{dut_epg_url}/a.channels.zip'.format(dut_epg_url=CONST_DUT_EPG_BASE)

    file = os.path.join("cache", "a.channels.json")
    tmp = os.path.join(ADDON_PROFILE, 'tmp', 'a.channels.zip')

    if not is_file_older_than_x_days(file=os.path.join(ADDON_PROFILE, file), days=1):
        return True
    else:
        resp = requests.get(channels_url, stream=True)

        if resp.status_code != 200:
            resp.close()
            return False

        with open(tmp, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=SESSION_CHUNKSIZE):
                f.write(chunk)
        
        resp.close()
        
        if os.path.isfile(tmp):
            from zipfile import ZipFile

            try:
                with ZipFile(tmp, 'r') as zipObj:
                    zipObj.extractall(os.path.join(ADDON_PROFILE, "cache", ""))
            except:
                try:
                    fixBadZipfile(tmp)

                    with ZipFile(tmp, 'r') as zipObj:
                        zipObj.extractall(os.path.join(ADDON_PROFILE, "cache", ""))
                except:
                    try:
                        from resources.lib.base.l1.zipfile import ZipFile as ZipFile2

                        with ZipFile2(tmp, 'r') as zipObj:
                            zipObj.extractall(os.path.join(ADDON_PROFILE, "cache", ""))
                    except:
                        return False
        else:
            return False

        clear_cache_connector()

    return True

def api_get_info(id, channel=''):
    pass

def _tmobile_addon_profile():
    return ADDON_PROFILE.replace(ADDON_ID, 'plugin.video.tmobile')

def _tmobile_profile_path(*parts):
    return os.path.join(_tmobile_addon_profile(), *parts)

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
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.45 Safari/537.36',
    }

    if csrf_token:
        headers['X_CSRFToken'] = csrf_token

    return headers

def _tmobile_write_ext_json(path, data):
    write_file(file=path, data=data, ext=True, isJSON=True)

def _tmobile_write_ext_text(path, data):
    write_file(file=path, data=data, ext=True, isJSON=False)

def _tmobile_save_session_state(profile, session):
    _tmobile_write_ext_json(_tmobile_profile_path('profile.json'), profile)
    _tmobile_write_ext_json(_tmobile_profile_path('stream_cookies'), session.cookies.get_dict())

def _tmobile_get_credentials(profile):
    username = ''
    password = ''

    if check_key(profile, 'username') and check_key(profile, 'pswd'):
        creds = Credentials().decode_credentials(profile['username'], profile['pswd'])
        username = creds.get('username', '')
        password = creds.get('password', '')

    return username, password

def _tmobile_login(session, profile):
    username, password = _tmobile_get_credentials(profile)

    if not username or not password:
        return False

    if not check_key(profile, 'devicekey'):
        return False

    login_url = 'https://tv.odido.nl/VSP/V3/Authenticate?from=throughMSAAccess'
    payload = {
        'authenticateBasic': {
            'VUID': '6_7_{devicekey}'.format(devicekey=profile['devicekey']),
            'clientPasswd': password,
            'isSupportWebpImgFormat': '0',
            'lang': 'nl',
            'needPosterTypes': ['1', '2', '3', '4', '5', '6', '7'],
            'timeZone': 'Europe/Amsterdam',
            'userID': username,
            'userType': '0',
        },
        'authenticateDevice': {
            'CADeviceInfos': [
                {
                    'CADeviceID': profile['devicekey'],
                    'CADeviceType': '7',
                },
            ],
            'deviceModel': '3103_PCClient',
            'physicalDeviceID': profile['devicekey'],
            'terminalID': profile['devicekey'],
        },
        'authenticateTolerant': {
            'areaCode': '',
            'bossID': '',
            'subnetID': '',
            'templateName': '',
            'userGroup': '',
        },
    }

    session.headers.update(_tmobile_headers())
    response = session.post(login_url, json=payload, timeout=20)

    try:
        data = response.json()
    except:
        data = None

    if response.status_code != 200 or not data or not check_key(data, 'result') or not check_key(data['result'], 'retCode') or data['result']['retCode'] != '000000000' or not check_key(data, 'csrfToken'):
        return False

    profile['csrf_token'] = data['csrfToken']
    profile['user_filter'] = data.get('userFilter', '')
    profile['last_login_success'] = 1
    profile['last_login_time'] = int(time.time())
    session.headers.update(_tmobile_headers(profile['csrf_token']))
    _tmobile_save_session_state(profile, session)

    return True

def _tmobile_get_session():
    profile = load_file(_tmobile_profile_path('profile.json'), ext=True, isJSON=True)

    if not profile:
        return None, None

    cookies = load_file(_tmobile_profile_path('stream_cookies'), ext=True, isJSON=True)

    if not cookies:
        cookies = {}

    session = requests.Session()
    session.headers.update(_tmobile_headers(profile.get('csrf_token', '')))
    session.cookies.update(cookies)

    heartbeat_url = 'https://tv.odido.nl/VSP/V3/OnLineHeartbeat?from=inMSAAccess'

    try:
        response = session.post(heartbeat_url, json={}, timeout=20)
        data = response.json()
    except:
        data = None
        response = None

    if not response or response.status_code != 200 or not data or not check_key(data, 'result') or not check_key(data['result'], 'retCode') or data['result']['retCode'] != '000000000':
        if not _tmobile_login(session, profile):
            session.close()
            return None, None

    return session, profile

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
    channels = load_file(_tmobile_profile_path('cache', 'channels.json'), ext=True, isJSON=True)

    if not channels:
        return None

    channel_ids = list(channels.keys())
    session, profile = _tmobile_get_session()

    if not session or not profile:
        return None

    try:
        programmes_by_channel = {}
        now = int(time.time())
        windows = []

        for day_offset in range(-7, 2):
            start_time = (now + (day_offset * 86400)) * 1000
            end_time = start_time + (86400 * 1000)
            windows.append((start_time, end_time))

        for channel_chunk in _tmobile_chunked(channel_ids, 20):
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
        _tmobile_save_session_state(profile, session)
        session.close()

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
        write_file(file=os.path.join('cache', 'tmobile', file_name), data=''.join(xml), ext=False, isJSON=False)
        written += 1

    _tmobile_write_ext_text(os.path.join(ADDON_PROFILE, 'tmp', 't.epg.timestamp'), str(int(time.time())))

    return written > 0

def _api_get_epg_by_tmobile():
    marker = os.path.join(ADDON_PROFILE, 'tmp', 't.epg.timestamp')
    cache_dir = os.path.join(ADDON_PROFILE, 'cache', 'tmobile')

    if os.path.isdir(cache_dir) and len(glob.glob(os.path.join(cache_dir, '*.xml'))) > 0 and not is_file_older_than_x_days(file=marker, days=0.5):
        return False

    programmes_by_channel = _tmobile_get_live_epg()

    if not programmes_by_channel:
        return False

    return _tmobile_write_epg_cache(programmes_by_channel)

def api_get_all_epg():
    updated = False

    profile_settings = load_profile(profile_id=1)

    for x in range(1, 6):
        if check_key(profile_settings, 'addon' + str(x)):
            if len(profile_settings['addon' + str(x)]) > 0:
                if api_get_epg_by_addon(profile_settings['addon' + str(x)].replace('plugin.video.', '')) == True:
                    updated = True

    clear_cache_connector()

    if updated == True:
        return True
    else:
        return False

def api_get_epg_by_addon(addon):
    if addon == 'tmobile':
        return _api_get_epg_by_tmobile()

    type = addon[0]
    directory = os.path.dirname(os.path.join(ADDON_PROFILE, 'tmp', 'epg.zip'))

    if not os.path.exists(directory):
        os.makedirs(directory)

    directory = os.path.dirname(os.path.join(ADDON_PROFILE, "cache", str(addon), 'epg.zip'))

    if not os.path.exists(directory):
        os.makedirs(directory)

    epg_url = '{dut_epg_url}/{type}.epg.zip'.format(dut_epg_url=CONST_DUT_EPG_BASE, type=type)
    tmp = os.path.join(ADDON_PROFILE, 'tmp', '{type}.epg.zip'.format(type=type))

    if not is_file_older_than_x_days(file=tmp, days=0.5):
        return False
    else:
        resp = requests.get(epg_url, stream=True)

        if resp.status_code != 200:
            resp.close()
            return False

        with open(tmp, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=SESSION_CHUNKSIZE):
                f.write(chunk)

        resp.close()

        if os.path.isfile(tmp):
            from zipfile import ZipFile

            try:
                with ZipFile(tmp, 'r') as zipObj:
                    zipObj.extractall(os.path.join(ADDON_PROFILE, "cache", str(addon), ""))
            except:
                try:
                    fixBadZipfile(tmp)

                    with ZipFile(tmp, 'r') as zipObj:
                        zipObj.extractall(os.path.join(ADDON_PROFILE, "cache", str(addon), ""))
                except:
                    try:
                        from resources.lib.base.l1.zipfile import ZipFile as ZipFile2

                        with ZipFile2(tmp, 'r') as zipObj:
                            zipObj.extractall(os.path.join(ADDON_PROFILE, "cache", str(addon), ""))
                    except:
                        return False
        else:
            return False

    return True
