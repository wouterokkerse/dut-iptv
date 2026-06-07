import base64, datetime, io, json, pytz, os, re, requests, sys, threading, time, xbmc, xbmcaddon, xbmcvfs, xbmcgui
import http.server as ProxyServer
import socketserver
import uuid

from collections import OrderedDict
from resources.lib.constants import *
from resources.lib.dnsutils import override_dns
from xml.dom.minidom import parseString
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

stream_url = {}
stream_base_url = {}
stream_license = {}
now_playing = 0
last_token = 0
audio_segments = {}
last_segment = 0
last_timecode = 0

ALLOWED_LICENSE_HEADERS = {}

ALLOWED_LICENSE_HEADERS['betelenet'] = [
    "User-Agent",
    "X-OESP-Content-Locator",
    "X-OESP-Username",
    "X-OESP-DRM-SchemeIdUri",
    "X-OESP-License-Token",
    "X-OESP-License-Token-Type", 
    "X-OESP-Token",
    "Content-Type",
    "Content-Length"
]

ALLOWED_LICENSE_HEADERS['videoland'] = [
    "User-Agent",
    "Authorization",
    "Content-Type",
    "Content-Length"
]

ALLOWED_LICENSE_HEADERS['ziggo'] = [
    "User-Agent",
    "X-OESP-Content-Locator",
    "X-OESP-Username",
    "X-OESP-DRM-SchemeIdUri",
    "X-OESP-License-Token",
    "X-OESP-License-Token-Type", 
    "X-OESP-Token",
    "Content-Type",
    "Content-Length"
]

ALLOWED_LICENSE_HEADERS['tmobile'] = [
    "User-Agent",
    "Accept",
    "Accept-Encoding",
    "Cookie",
    "AcquireLicense.CustomData",
    "CADeviceType",
    "Content-Type",
    "X_CSRFToken",
    "Origin",
    "Referer",
]

class HTTPMonitor(xbmc.Monitor):
    def __init__(self, addon):
        super(HTTPMonitor, self).__init__()
        self.addon = addon

class HTTPServer(socketserver.ThreadingMixIn, ProxyServer.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, addon, server_address):
        ProxyServer.HTTPServer.__init__(self, server_address, HTTPRequestHandler)
        self.addon = addon

class HTTPRequestHandler(ProxyServer.BaseHTTPRequestHandler):
    def _get_addon_name(self):
        if "/betelenet/" in self.path:
            return 'betelenet'
        if "/canaldigitaal/" in self.path:
            return 'canaldigitaal'
        if "/kpn/" in self.path:
            return 'kpn'
        if "/nlziet/" in self.path:
            return 'nlziet'
        if "/tmobile/" in self.path:
            return 'tmobile'
        if "/videoland/" in self.path:
            return 'videoland'
        if "/ziggo/" in self.path:
            return 'ziggo'

        return None

    def do_POST(self):
        addon_name = self._get_addon_name()

        if not addon_name:
            self.send_response(404)
            self.end_headers()

            try:
                self.connection.close()
            except:
                pass

            return

        self.path = self.path.replace('{addon_name}/'.format(addon_name=addon_name), '', 1)

        ADDON = xbmcaddon.Addon(id="plugin.video.{addon_name}".format(addon_name=addon_name))
        ADDON_PROFILE = xbmcvfs.translatePath(ADDON.getAddonInfo('profile'))
        
        if "/license" in self.path:
            if os.path.isfile(ADDON_PROFILE + 'stream_license'):
                stream_license[addon_name] = load_file(file=ADDON_PROFILE + 'stream_license', isJSON=False)

                try:
                    os.remove(ADDON_PROFILE + 'stream_license')
                except:
                    pass
                    
            data = self.rfile.read(int(self.headers['Content-Length']))
            headers = {}
                        
            for header in self.headers:
                if check_key(ALLOWED_LICENSE_HEADERS, addon_name):                
                    if header in ALLOWED_LICENSE_HEADERS[addon_name]:
                        headers[header] = self.headers[header]
                else:
                    headers[header] = self.headers[header]
            
            write_file(file=ADDON_PROFILE + 'license_headers', data=headers, isJSON=True)
            write_file(file=ADDON_PROFILE + 'license_data', data=base64.b64encode(data).decode('utf-8'), isJSON=False)
            
            write_file(file=ADDON_PROFILE + 'license_url', data=str(stream_license[addon_name]), isJSON=False)

            if addon_name == 'tmobile':
                session = proxy_get_session(proxy=self, addon_name=addon_name)
                req_headers = dict(session.headers)
                req_headers.update(headers)
                req_headers.pop('Host', None)
                req_headers.pop('Content-Length', None)
                r = session.post(stream_license[addon_name], headers=req_headers, data=data)
                write_file(file=ADDON_PROFILE + 'license_upstream_headers', data=dict(r.request.headers), isJSON=True)
            else:
                r = requests.post(stream_license[addon_name], headers=headers, data=data)

            write_file(file=ADDON_PROFILE + 'license_response_data', data=base64.b64encode(r.content).decode('utf-8'), isJSON=False)
            self.send_response(r.status_code)

            for header in r.headers:
                self.send_header(header, r.headers[header])

            self.end_headers()
            r.close()

            try:
                self.wfile.write(r.content)
            except:
                pass

            try:
                self.connection.close()
            except:
                pass
        else:
            self.send_response(501)
            self.end_headers()
            
            try:
                self.connection.close()
            except:
                pass
        
    def do_GET(self):
        global stream_url, now_playing, last_token, audio_segments, last_segment, last_timecode

        if "/status" in self.path:
            self.send_response(200)
            self.send_header('X-TEST', 'OK')
            self.end_headers()
        else:
            addon_name = self._get_addon_name()

            if not addon_name:
                self.send_response(404)
                self.end_headers()

                try:
                    self.connection.close()
                except:
                    pass

                return

            self.path = self.path.replace('{addon_name}/'.format(addon_name=addon_name), '', 1)

            ADDON = xbmcaddon.Addon(id="plugin.video.{addon_name}".format(addon_name=addon_name))
            ADDON_PROFILE = xbmcvfs.translatePath(ADDON.getAddonInfo('profile'))
                
            if proxy_get_match(path=self.path, addon_name=addon_name) and os.path.isfile(ADDON_PROFILE + 'stream_hostname'):
                stream_url[addon_name] = load_file(file=ADDON_PROFILE + 'stream_hostname', isJSON=False)

                try:
                    os.remove(ADDON_PROFILE + 'stream_hostname')
                except:
                    pass

                now_playing = int(time.time())
                last_token = int(time.time()) + 60

                URL = proxy_get_url(proxy=self, addon_name=addon_name, ADDON_PROFILE=ADDON_PROFILE)

                if addon_name == 'kpn':
                    start = load_file(file=ADDON_PROFILE + 'stream_start', isJSON=False)

                    if start:
                        startT = datetime.datetime.fromtimestamp(int(start))
                        mytz = pytz.timezone('Europe/Amsterdam')
                        startTUTC = mytz.normalize(mytz.localize(startT, is_dst=True)).astimezone(pytz.timezone('UTC'))
                        URL += '&t={date1}%3A{date2}%3A{date3}.000'.format(date1=startTUTC.strftime('%Y-%m-%dT%H'), date2=startTUTC.strftime('%M'), date3=startTUTC.strftime('%S'))

                session = proxy_get_session(proxy=self, addon_name=addon_name)
                r = session.get(URL)

                if addon_name == 'tmobile':
                    final_url = r.url

                    if '/PLTV/' in final_url:
                        stream_base_url[addon_name] = final_url.split('/PLTV/', 1)[0] + '/'

                xml = r.text

                if addon_name == 'tmobile' and 'mpd' in xml.lower():
                    retry_url = tmobile_build_browser_style_mpd_url(URL, xml)

                    if retry_url != URL:
                        r_retry = session.get(retry_url)

                        if r_retry.status_code == 200 and 'mpd' in r_retry.text.lower():
                            r.close()
                            r = r_retry
                            URL = retry_url
                            xml = r.text

                            final_url = r.url

                            if '/PLTV/' in final_url:
                                stream_base_url[addon_name] = final_url.split('/PLTV/', 1)[0] + '/'
                        else:
                            r_retry.close()

                if 'mpd' in xml.lower():
                    write_file(file=ADDON_PROFILE + 'full_url', data=URL, isJSON=False)
                    write_file(file=ADDON_PROFILE + 'final_url', data=r.url, isJSON=False)
                    if addon_name == 'tmobile' and addon_name in stream_base_url:
                        write_file(file=ADDON_PROFILE + 'stream_base_url', data=stream_base_url[addon_name], isJSON=False)
                    write_file(file=ADDON_PROFILE + 'orig.mpd', data=xml, isJSON=False)

                    preserve_structure = addon_name == 'tmobile' and (
                        'urn:uuid:edef8ba9-79d6-4ace-a3c8-27dcd51d21ed' in xml or
                        'urn:uuid:9a04f079-9840-4286-ab92-e65be0885f95' in xml
                    )

                    xml = sly_mpd_parse(data=xml, preserve_structure=preserve_structure).decode('utf-8')

                    write_file(file=ADDON_PROFILE + 'after_sly_mpd_parse.mpd', data=xml, isJSON=False)

                    if not preserve_structure:
                        xml = mpd_parse(data=xml, addon_name=addon_name, URL=URL).decode('utf-8')

                    write_file(file=ADDON_PROFILE + 'after_mpd_parse.mpd', data=xml, isJSON=False)

                self.send_response(r.status_code)

                r.headers['Content-Length'] = len(xml)

                for header in r.headers:
                    if not 'Content-Encoding' in header and not 'Transfer-Encoding' in header:
                        self.send_header(header, r.headers[header])

                self.end_headers()
                r.close()

                try:
                    xml = xml.encode('utf-8')
                except:
                    pass

                try:
                    self.wfile.write(xml)
                except:
                    pass

                try:
                    self.connection.close()
                except:
                    pass
            else:
                URL = proxy_get_url(proxy=self, addon_name=addon_name, ADDON_PROFILE=ADDON_PROFILE)

                if addon_name == "kpn" and 'npo1-audio_dut=128000-' in URL.lower():
                    URL = fix_audio(URL)

                now_playing = int(time.time())

                if (addon_name == 'betelenet' or addon_name == 'ziggo') and last_token < now_playing:
                    token_renew = load_file(file=ADDON_PROFILE + 'token_renew', isJSON=False)
                    xbmc.executebuiltin('RunPlugin(%s)' % (token_renew))
                    last_token = int(time.time()) + 60

                if addon_name == 'tmobile':
                    session = proxy_get_session(proxy=self, addon_name=addon_name)
                    write_file(file=ADDON_PROFILE + 'proxy_request_headers', data=dict(session.headers), isJSON=True)
                    r = session.get(URL, stream=True)
                    write_file(file=ADDON_PROFILE + 'proxy_prepared_headers', data=dict(r.request.headers), isJSON=True)

                    if r.status_code >= 400:
                        write_file(file=ADDON_PROFILE + 'proxy_error_url', data=URL, isJSON=False)
                        write_file(file=ADDON_PROFILE + 'proxy_error_status', data=str(r.status_code), isJSON=False)
                        write_file(file=ADDON_PROFILE + 'proxy_error_headers', data=dict(r.headers), isJSON=True)
                        write_file(file=ADDON_PROFILE + 'proxy_error_body', data=r.text[:1000], isJSON=False)

                    self.send_response(r.status_code)

                    if 'Content-Length' in r.headers:
                        self.send_header('Content-Length', r.headers['Content-Length'])

                    for header in r.headers:
                        if not 'Content-Encoding' in header and not 'Transfer-Encoding' in header and not 'Content-Length' in header:
                            self.send_header(header, r.headers[header])

                    self.end_headers()

                    try:
                        for chunk in r.iter_content(chunk_size=65536):
                            if not chunk:
                                continue
                            self.wfile.write(chunk)
                    except:
                        pass

                    r.close()
                else:
                    self.send_response(302)
                    self.send_header('Location', URL)
                    self.end_headers()

                try:
                    self.connection.close()
                except:
                    pass

    def log_message(self, format, *args):
        return

class RemoteControlBrowserService(xbmcaddon.Addon):
    def __init__(self):
        super(RemoteControlBrowserService, self).__init__()
        self.pluginId = self.getAddonInfo('id')

        self.addonFolder = xbmcvfs.translatePath(self.getAddonInfo('path'))
        self.profileFolder = xbmcvfs.translatePath(self.getAddonInfo('profile'))

        self.settingsChangeLock = threading.Lock()
        self.isShutdown = False
        self.HTTPServer = None
        self.HTTPServerThread = None

    def clearBrowserLock(self):
        """Clears the pidfile in case the last shutdown was not clean"""
        browserLockPath = os.path.join(self.profileFolder, 'browser.pid')
        try:
            os.remove(browserLockPath)
        except OSError:
            pass

    def reloadHTTPServer(self):
        with self.settingsChangeLock:
            self.startHTTPServer()

    def shutdownHTTPServer(self):
        with self.settingsChangeLock:
            self.stopHTTPServer()
            self.isShutdown = True

    def startHTTPServer(self):
        if self.isShutdown:
            return

        self.stopHTTPServer()

        try:
            self.HTTPServer = HTTPServer(self, ('', 11189))
        except IOError as e:
            pass

        threadStarting = threading.Thread(target=self.HTTPServer.serve_forever)
        threadStarting.start()
        self.HTTPServerThread = threadStarting

    def stopHTTPServer(self):
        if self.HTTPServer is not None:
            self.HTTPServer.shutdown()
            self.HTTPServer = None
        if self.HTTPServerThread is not None:
            self.HTTPServerThread.join()
            self.HTTPServerThread = None

class Session(requests.Session):
    def __init__(self, addon_name='', headers=None, cookies_key=None, save_cookies=True, base_url='{}', timeout=None, attempts=None):
        super(Session, self).__init__()

        base_headers = CONST_BASE_HEADERS[addon_name]
        base_headers.update({'User-Agent': DEFAULT_USER_AGENT})

        if headers:
            base_headers.update(headers)

        self._headers = base_headers or {}
        self._cookies_key = cookies_key
        self._save_cookies = save_cookies
        self._base_url = base_url
        self._timeout = timeout or (5, 10)
        self._attempts = attempts or 2
        self._addon_name = addon_name

        ADDON = xbmcaddon.Addon(id="plugin.video." + addon_name)

        self._addon_profile = xbmcvfs.translatePath(ADDON.getAddonInfo('profile'))

        if addon_name == 'tmobile':
            profile = load_file(file=self._addon_profile + 'profile.json', isJSON=True)

            if profile and check_key(profile, 'csrf_token'):
                self._headers.update({'X_CSRFToken': profile['csrf_token']})

        self.headers.update(self._headers)

        if self._cookies_key:
            try:
                cookies = load_file(file=self._addon_profile + 'stream_cookies', isJSON=True)
            except:
                cookies = {}

            self.cookies.update(cookies)

    def request(self, method, url, timeout=None, attempts=None, **kwargs):
        if not url.startswith('http'):
            url = self._base_url.format(url)

        kwargs['timeout'] = timeout or self._timeout
        attempts = attempts or self._attempts

        if sys.version_info < (3, 0):
            rngattempts = range(1, attempts+1)
        else:
            rngattempts = list(range(1, attempts+1))

        for i in rngattempts:
            #log.debug('Attempt {}/{}: {} {} {}'.format(i, attempts, method, url, kwargs if method.lower() != 'post' else ""))

            try:
                if (self._addon_name == 'betelenet' or self._addon_name == 'ziggo'):
                    override_dns(CONST_BASE_DOMAIN[self._addon_name], CONST_BASE_IP[self._addon_name])

                data = super(Session, self).request(method, url, **kwargs)

                if self._cookies_key and self._save_cookies:
                    self.save_cookies(ADDON_PROFILE=self._addon_profile)

                return data
            except:
                if i == attempts:
                    raise

    def save_cookies(self, ADDON_PROFILE):
        if not self._cookies_key:
            raise Exception('A cookies key needs to be set to save cookies')

        write_file(file=ADDON_PROFILE + 'stream_cookies', data=self.cookies.get_dict(), isJSON=True)

    def clear_cookies(self):
        self.cookies.clear()

    def chunked_dl(self, url, dst_path, method='GET'):
        resp = self.request(method, url, stream=True)
        resp.raise_for_status()

        with open(dst_path, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=4096):
                f.write(chunk)

def main():
    global now_playing

    service = RemoteControlBrowserService()
    service.clearBrowserLock()
    monitor = HTTPMonitor(service)

    loop = True

    while loop == True:
        xbmc.log('(RE)START DUT-IPTV PROXY')
        service.reloadHTTPServer()

        if monitor.waitForAbort(3600):
            loop = False

        while int(now_playing) + 120 > int(time.time()) and loop == True:
            if monitor.waitForAbort(600):
                loop = False

    service.shutdownHTTPServer()

def sly_mpd_parse(data, preserve_structure=False):
    data = data.replace('_xmlns:cenc', 'xmlns:cenc')
    data = data.replace('_:default_KID', 'cenc:default_KID')
    data = data.replace('<pssh', '<cenc:pssh')
    data = data.replace('</pssh>', '</cenc:pssh>')

    root = parseString(data.encode('utf8'))

    mpd = root.getElementsByTagName("MPD")[0]

    ## Set publishtime to utctime
    utc_time = mpd.getElementsByTagName("UTCTiming")
    if utc_time:
        value = utc_time[0].getAttribute('value')
        mpd.setAttribute('publishTime', value)

    for elem in mpd.getElementsByTagName("SupplementalProperty"):
        if elem.getAttribute('schemeIdUri') == 'urn:scte:dash:utc-time':
            value = elem.getAttribute('value')
            mpd.setAttribute('publishTime', value)
            break

    if not preserve_structure:
        base_url_nodes = []

        for node in mpd.childNodes:
            if node.nodeType == node.ELEMENT_NODE:
                if node.localName == 'BaseURL':
                    base_url_nodes.append(node)

        if base_url_nodes:
            base_url_nodes.pop(0)

            for e in base_url_nodes:
                e.parentNode.removeChild(e)

        if 'type' in mpd.attributes.keys() and mpd.getAttribute('type').lower() == 'dynamic':
            periods = [elem for elem in root.getElementsByTagName('Period')]

            if len(periods) > 1:
                periods.pop()
                for e in periods:
                    e.parentNode.removeChild(e)

    for elem in root.getElementsByTagName('AudioChannelConfiguration'):
        if elem.getAttribute('schemeIdUri') == 'tag:dolby.com,2014:dash:audio_channel_configuration:2011':
            elem.setAttribute('schemeIdUri', 'urn:dolby:dash:audio_channel_configuration:2011')

    if not preserve_structure:
        for elem in root.getElementsByTagName('Representation'):
            parent = elem.parentNode
            parent.removeChild(elem)
            parent.appendChild(elem)

    for adap_set in root.getElementsByTagName('AdaptationSet'):
        content_protections = adap_set.getElementsByTagName('ContentProtection')
        has_default_kid = False
        default_kid = None

        for cp in content_protections:
            if cp.getAttribute('cenc:default_KID') or cp.getAttribute('default_KID'):
                has_default_kid = True
                break

        if has_default_kid:
            continue

        for cp in content_protections:
            for pro in cp.getElementsByTagName('mspr:pro'):
                try:
                    pro_xml = base64.b64decode(''.join(
                        node.data for node in pro.childNodes if node.nodeType == node.TEXT_NODE
                    )).decode('utf-16-le', errors='ignore')
                    match = re.search(r'<KID>([^<]+)</KID>', pro_xml)

                    if not match:
                        continue

                    kid_bytes = bytearray(base64.b64decode(match.group(1)))
                    kid_be = bytes(kid_bytes[3::-1] + kid_bytes[5:3:-1] + kid_bytes[7:5:-1] + kid_bytes[8:16])
                    default_kid = str(uuid.UUID(bytes=kid_be))
                    break
                except:
                    pass

            if default_kid:
                break

        if not default_kid:
            continue

        mp4prot = None

        for cp in content_protections:
            if cp.getAttribute('schemeIdUri') == 'urn:mpeg:dash:mp4protection:2011':
                mp4prot = cp
                break

        if mp4prot is None and content_protections:
            mp4prot = content_protections[0]

        if mp4prot is not None:
            mp4prot.setAttribute('cenc:default_KID', default_kid)

    if not preserve_structure:
        video_sets = []
        other_sets = []
        trick_sets = []

        for adap_set in root.getElementsByTagName('AdaptationSet'):
            highest_bandwidth = 0
            is_video = False
            is_trick = False

            adapt_frame_rate = adap_set.getAttribute('frameRate')
            if adapt_frame_rate and '/' not in adapt_frame_rate:
                adapt_frame_rate = None

            if adapt_frame_rate:
                adap_set.removeAttribute('frameRate')

            if 'video' in adap_set.getAttribute('mimeType'):
                is_video = True

            for stream in adap_set.getElementsByTagName("Representation"):
                attrib = {}

                for key in adap_set.attributes.keys():
                    attrib[key] = adap_set.getAttribute(key)

                for key in stream.attributes.keys():
                    attrib[key] = stream.getAttribute(key)

                if adapt_frame_rate and not stream.getAttribute('frameRate'):
                    stream.setAttribute('frameRate', adapt_frame_rate)

                if 'bandwidth' in attrib:
                    bandwidth = int(attrib['bandwidth'])
                    if bandwidth > highest_bandwidth:
                        highest_bandwidth = bandwidth

                if 'maxPlayoutRate' in attrib:
                    is_video = False
                    is_trick = True

            parent = adap_set.parentNode
            parent.removeChild(adap_set)

            if is_trick:
                trick_sets.append([highest_bandwidth, adap_set, parent])
            elif is_video:
                video_sets.append([highest_bandwidth, adap_set, parent])
            else:
                other_sets.append([highest_bandwidth, adap_set, parent])

        video_sets.sort(key=lambda  x: x[0], reverse=True)
        trick_sets.sort(key=lambda  x: x[0], reverse=True)
        other_sets.sort(key=lambda  x: x[0], reverse=True)

        for elem in video_sets:
            elem[2].appendChild(elem[1])

        for elem in trick_sets:
            elem[2].appendChild(elem[1])

        for elem in other_sets:
            elem[2].appendChild(elem[1])

    elems = root.getElementsByTagName('SegmentTemplate')
    elems.extend(root.getElementsByTagName('SegmentURL'))

    for e in elems:
        def process_attrib(attrib):
            if attrib not in e.attributes.keys():
                return

        process_attrib('initialization')
        process_attrib('media')

        if 'presentationTimeOffset' in e.attributes.keys():
            e.removeAttribute('presentationTimeOffset')

    return root.toxml(encoding='utf-8')

def mpd_parse(data, addon_name, URL):
    global audio_segments, last_segment, last_timecode

    audio_segments = {}
    temp_segments = {}
    temp_audio_segments = []
    ac3_found = False

    root = parseString(data.encode('utf8'))
    mpd = root.getElementsByTagName("MPD")[0]

    ADDON = xbmcaddon.Addon(id="plugin.video." + addon_name)
    ADDON_PROFILE = xbmcvfs.translatePath(ADDON.getAddonInfo('profile'))

    duration = load_file(file=ADDON_PROFILE + 'stream_duration', isJSON=False)

    if duration and int(duration) > 0 and 'mediaPresentationDuration' in mpd.attributes.keys():
        duration = int(duration)
        given_duration = 0
        given_day = 0
        given_hour = 0
        given_minute = 0
        given_second = 0

        duration += ADDON.getSettingInt("add_duration")

        mediaPresentationDuration = mpd.getAttribute('mediaPresentationDuration').lower()

        regex = r"pt([0-9]*)[d]*([0-9]*)[h]*([0-9]*)[m]*([0-9]*)[s]*"
        matches = re.finditer(regex, mediaPresentationDuration)

        for matchNum, match in enumerate(matches, start=1):
            if not match.group(1):
                continue
            elif not match.group(4):
                given_second = int(match.group(1))
            elif not match.group(3):
                given_minute = int(match.group(1))
                given_second = int(match.group(4))
            elif not match.group(2):
                given_hour = int(match.group(1))
                given_minute = int(match.group(3))
                given_second = int(match.group(4))
            else:
                given_day = int(match.group(1))
                given_hour = int(match.group(2))
                given_minute = int(match.group(3))
                given_second = int(match.group(4))

            given_duration = (given_day * 24* 60 * 60) + (given_hour * 60 * 60) + (given_minute * 60) + given_second

        if not given_duration > 0 or given_duration > duration:
            minute, second = divmod(duration, 60)
            hour, minute = divmod(minute, 60)

            mpd.setAttribute('mediaPresentationDuration', 'PT{hour}H{minute}M{second}S'.format(hour=hour, minute=minute, second=second))

    prefered_language = load_file(file=ADDON_PROFILE + 'stream_language', isJSON=False)

    try:
        prefered_language = AUDIO_LANGUAGES_REV[prefered_language]
    except:
        pass

    for adap_set in root.getElementsByTagName('AdaptationSet'):
        if 'audio' in adap_set.getAttribute('mimeType'):
            for stream in adap_set.getElementsByTagName("Representation"):
                attrib = {}

                for key in adap_set.attributes.keys():
                    attrib[key] = adap_set.getAttribute(key)

                for key in stream.attributes.keys():
                    attrib[key] = stream.getAttribute(key)

                if prefered_language and check_key(attrib, 'lang') and attrib['lang'].lower() != prefered_language:
                    parent = stream.parentNode
                    parent.removeChild(stream)
                    continue

                try:
                    if attrib['codecs'].lower() == 'ac-3':
                        ac3_found = True
                except:
                    pass
        elif 'video' in adap_set.getAttribute('mimeType') and ADDON.getSettingBool('force_highest_bandwidth'):
            highest_bandwidth = 0
            is_video = True
            is_trick = False

            for stream in adap_set.getElementsByTagName("Representation"):
                attrib = {}

                for key in adap_set.attributes.keys():
                    attrib[key] = adap_set.getAttribute(key)

                for key in stream.attributes.keys():
                    attrib[key] = stream.getAttribute(key)

                if 'bandwidth' in attrib:
                    bandwidth = int(attrib['bandwidth'])
                    if bandwidth > highest_bandwidth:
                        highest_bandwidth = bandwidth

                if 'maxPlayoutRate' in attrib:
                    is_video = False
                    is_trick = True

            if is_trick:
                for stream in adap_set.getElementsByTagName("Representation"):
                    attrib = {}

                    for key in adap_set.attributes.keys():
                        attrib[key] = adap_set.getAttribute(key)

                    for key in stream.attributes.keys():
                        attrib[key] = stream.getAttribute(key)

                    if 'bandwidth' in attrib and 'maxPlayoutRate' in attrib:
                        bandwidth = int(attrib['bandwidth'])

                        if bandwidth != highest_bandwidth:
                            parent = stream.parentNode
                            parent.removeChild(stream)
            elif is_video:
                for stream in adap_set.getElementsByTagName("Representation"):
                    attrib = {}

                    for key in adap_set.attributes.keys():
                        attrib[key] = adap_set.getAttribute(key)

                    for key in stream.attributes.keys():
                        attrib[key] = stream.getAttribute(key)

                    if 'bandwidth' in attrib and not 'maxPlayoutRate' in attrib:
                        bandwidth = int(attrib['bandwidth'])

                        if bandwidth != highest_bandwidth:
                            parent = stream.parentNode
                            parent.removeChild(stream)

    if ac3_found == True and ADDON.getSettingBool('force_ac3'):
        for adap_set in root.getElementsByTagName('AdaptationSet'):
            if 'audio' in adap_set.getAttribute('mimeType'):
                for stream in adap_set.getElementsByTagName("Representation"):
                    attrib = {}

                    for key in adap_set.attributes.keys():
                        attrib[key] = adap_set.getAttribute(key)

                    for key in stream.attributes.keys():
                        attrib[key] = stream.getAttribute(key)

                    try:
                        if not attrib['codecs'].lower() == 'ac-3':
                            parent = stream.parentNode
                            parent.removeChild(stream)
                    except:
                        pass

    if addon_name == "kpn" and 'npo1' in URL.lower():
        last_segment = 0
        last_timecode = 0

        for adap_set in root.getElementsByTagName('AdaptationSet'):
            if 'audio' in adap_set.getAttribute('mimeType'):
                for segmenttimeline in adap_set.getElementsByTagName("SegmentTimeline"):
                    for segment in segmenttimeline.getElementsByTagName("S"):
                        if not 'd' in segment.attributes.keys():
                            continue

                        temp_segments[segment.getAttribute('d')] = 1

    for segment in temp_segments:
        temp_audio_segments.append(segment)

    last = 0
    count = int(len(temp_audio_segments)) - 1

    temp_audio_segments.reverse()

    for segment in temp_audio_segments:
        if last == 0:
            audio_segments[segment] = temp_audio_segments[count]
        else:
            audio_segments[segment] = last

        last = segment
                
    for adap_set in root.getElementsByTagName('AdaptationSet'):
        if len(adap_set.getElementsByTagName("Representation")) == 0:
            parent = adap_set.parentNode
            parent.removeChild(adap_set)

    return root.toxml(encoding='utf-8')

def fix_audio(URL):
    global audio_segments, last_segment, last_timecode

    old_last_timecode = 0
    temp_last_timecode = 0

    try:
        if int(URL.replace('.dash', '').rsplit('-', 1)[1]) < last_timecode:
            last_segment = 0
            last_timecode = 0

        if last_segment == 0 and last_timecode == 0:
            last_timecode = int(URL.replace('.dash', '').rsplit('-', 1)[1])
        elif last_segment == 0:
            old_last_timecode = last_timecode
            last_timecode = int(URL.replace('.dash', '').rsplit('-', 1)[1])
            last_segment = int(last_timecode - old_last_timecode)
        else:
            old_last_timecode = last_timecode
            last_timecode = int(URL.replace('.dash', '').rsplit('-', 1)[1])

            if (last_timecode - old_last_timecode) != audio_segments[str(last_segment)]:
                temp_last_timecode = last_timecode
                last_timecode = int(old_last_timecode + int(audio_segments[str(last_segment)]))
                last_segment = int(audio_segments[str(last_segment)])

                URL = URL.replace(str(temp_last_timecode), str(last_timecode))
            else:
                last_segment = int(last_timecode - old_last_timecode)
    except:
        pass

    return URL

def check_key(object, key):
    if key in object and object[key] and len(str(object[key])) > 0:
        return True
    else:
        return False

def load_file(file, isJSON=False):
    if not os.path.isfile(file):
        return None

    with io.open(file, 'r', encoding='utf-8') as f:
        if isJSON == True:
            return json.load(f, object_pairs_hook=OrderedDict)
        else:
            return f.read()

def proxy_get_match(path, addon_name):
    if addon_name == 'betelenet' or addon_name == 'ziggo':
        if "manifest.mpd" in path or "Manifest" in path:
            return True
    else:
        if ".mpd" in path:
            return True

    return False

def proxy_get_session(proxy, addon_name):
    if addon_name == 'betelenet' or addon_name == 'ziggo':
        HEADERS = CONST_BASE_HEADERS[addon_name]

        for header in proxy.headers:
            if proxy.headers[header] is not None and header in CONST_ALLOWED_HEADERS[addon_name]:
                HEADERS[header] = proxy.headers[header]

        return Session(addon_name=addon_name, headers=HEADERS)

    else:
        return Session(addon_name=addon_name, cookies_key='cookies', save_cookies=False)

def proxy_get_url(proxy, addon_name, ADDON_PROFILE):
    global stream_url, stream_base_url
    path = str(proxy.path)

    if addon_name == 'betelenet' or addon_name == 'ziggo':
        return stream_url[addon_name] + path.replace('WIDEVINETOKEN', load_file(file=ADDON_PROFILE + 'widevine_token', isJSON=False))
    elif addon_name == 'tmobile':
        path_no_slash = path.lstrip('/')

        if path_no_slash.startswith('PLTV/') and addon_name in stream_base_url:
            return stream_base_url[addon_name] + path_no_slash

        return stream_url[addon_name] + path
    else:
        return stream_url[addon_name] + path

def tmobile_build_browser_style_mpd_url(url, xml):
    if 'hms_devid=' in url and 'mag_hms=' in url and 'RTS=' in url and 'from=' in url:
        return url

    service_match = re.search(r'service_devid=([^&"]+)', xml)
    mag_match = re.search(r'mag_hms=([^&"]+)', xml)
    online_match = re.search(r'online=([^&"]+)', xml)
    pltv_match = re.search(r'/PLTV/([^/]+)/', url)

    if not service_match or not mag_match or not online_match:
        return url

    parsed = urlparse(url)
    query = OrderedDict(parse_qsl(parsed.query, keep_blank_values=True))

    query['hms_devid'] = service_match.group(1)
    query['mag_hms'] = mag_match.group(1)
    query['online'] = online_match.group(1)
    query['RTS'] = online_match.group(1)
    query['_'] = str(int(time.time() * 1000))

    if 'from' not in query:
        query['from'] = '14'

    if 'icpid' not in query or not query['icpid']:
        if pltv_match:
            query['icpid'] = pltv_match.group(1)

    return urlunparse(parsed._replace(query=urlencode(query)))

def write_file(file, data, isJSON=False):
    with io.open(file, 'w', encoding="utf-8") as f:
        if isJSON == True:
            f.write(json.dumps(data, ensure_ascii=False))
        else:
            f.write(data)

if __name__ == "__main__":
    main()
