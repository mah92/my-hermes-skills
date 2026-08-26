#!/usr/bin/env python3
"""Cast to an LG webOS TV DLNA renderer (the picky one).

Why separate from cast.py: LG (at least LF6300-era webOS) rejects plain
SOAP (error 714 Illegal MIME-type) unless the payload uses:
  - SOAP-ENV prefix + dt:dt datatype attributes on every arg
  - DIDL-Lite where <res> has NO protocolInfo attribute, restricted="0",
    and the metadata is XML-escaped inside the CDATA/arg text
  - optional <upnp:class> element
The resource URL also MUST answer HEAD (501 => UPnP 716 "Resource not found").
LG replies only to unicast SSDP (multicast ignored).

Usage:
  python3 cast_lg.py <file.mp4|http://...> ["Title"] [tv_ip]
PREREQ: scripts/range_server.py running (it now answers HEAD/GET/OPTIONS).
"""
import os, re, socket, struct, subprocess, sys, time, urllib.request, urllib.error

AV = "urn:schemas-upnp-org:service:AVTransport:1"
TARGET = sys.argv[3] if len(sys.argv) > 3 else "192.168.1.104"

def own_ip():
    try:
        out = subprocess.check_output(["hostname", "-I"]).decode().split()
        for ip in out:
            if ip.startswith("192.168."):
                return ip
    except Exception:
        pass
    return "192.168.1.108"

def discover(target):
    def unicast_probe():
        us = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        us.settimeout(3.0)
        msg = ("M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\n"
               "MAN: \"ssdp:discover\"\r\nMX: 2\r\n"
               "ST: urn:schemas-upnp-org:device:MediaRenderer:1\r\n\r\n").encode()
        try:
            for _ in range(3):
                us.sendto(msg, (target, 1900))
                try:
                    data, _ = us.recvfrom(8192)
                    for line in data.decode("utf-8", "replace").split("\r\n"):
                        if line.lower().startswith("location:"):
                            return line.split(":", 1)[1].strip()
                except socket.timeout:
                    pass
        finally:
            us.close()
        return None
    loc = unicast_probe()
    if not loc:
        sys.exit("renderer at %s did not answer unicast SSDP — is it ON?" % target)
    root = urllib.request.urlopen(loc, timeout=8).read().decode("utf-8", "replace")
    m = re.search(r"<controlURL>(.*?AVTransport.*?)</controlURL>", root, re.S)
    if not m: sys.exit("AVTransport controlURL not found")
    cu = m.group(1).strip()
    return cu if cu.startswith("http") else loc.rstrip("/") + cu

def soap(action, args, ctrl):
    body = (f'<?xml version="1.0"?>'
            f'<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/" '
            f'SOAP-ENV:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
            f'<SOAP-ENV:Body>'
            f'<m:{action} xmlns:m="{AV}">{args}</m:{action}>'
            f'</SOAP-ENV:Body></SOAP-ENV:Envelope>')
    req = urllib.request.Request(ctrl, data=body.encode(),
        headers={"Content-Type": 'text/xml; charset="utf-8"', "SOAPAction": f'"{AV}#{action}"'})
    try:
        return urllib.request.urlopen(req, timeout=15).read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.read().decode("utf-8", "replace")

def tag(r, t):
    m = re.search(r"<%s>(.*?)</%s>" % (t, t), r, re.S)
    return m.group(1).strip() if m else None

if len(sys.argv) < 2:
    sys.exit(__doc__)
media = sys.argv[1]
title = sys.argv[2] if len(sys.argv) > 2 else "Stream"
if not media.startswith("http"):
    src = media
    media = "http://%s:8000/%s" % (own_ip(), os.path.basename(src))
    print("serving file as:", media)
try:
    urllib.request.urlopen(media, timeout=6)
except Exception as e:
    sys.exit("media url not reachable — is range_server.py running? (%s)" % e)

ctrl = discover(TARGET)
print("controlURL:", ctrl)

DT = ' xmlns:dt="urn:schemas-microsoft-com:datatypes"'
didl = ('&lt;DIDL-Lite xmlns=&quot;urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/&quot; '
        'xmlns:dc=&quot;http://purl.org/dc/elements/1.1/&quot; '
        'xmlns:upnp=&quot;urn:schemas-upnp-org:metadata-1-0/upnp/&quot; '
        'xmlns:dlna=&quot;urn:schemas-dlna-org:device-1-0&quot;&gt;'
        '&lt;item id=&quot;36e9bdbfd26503888b0833bcc5110712a&quot; parentID=&quot;8&quot; restricted=&quot;0&quot;&gt;'
        '&lt;upnp:class&gt;object.item.videoItem&lt;/upnp:class&gt;'
        f'&lt;dc:title&gt;{title}&lt;/dc:title&gt;'
        f'&lt;res&gt;{media}&lt;/res&gt;'
        '&lt;/item&gt;&lt;/DIDL-Lite&gt;')

r = soap("SetAVTransportURI",
         f'<InstanceID{DT} dt:dt="ui4">0</InstanceID>'
         f'<CurrentURI{DT} dt:dt="string">{media}</CurrentURI>'
         f'<CurrentURIMetaData{DT} dt:dt="string">{didl}</CurrentURIMetaData>', ctrl)
if "errorCode" in r:
    ec = re.search(r"errorCode>(\d+)", r)
    print("SetAVTransportURI FAILED, errorCode:", ec.group(1) if ec else "?")
    print(re.sub(r"\s+", " ", r)[:300])
    sys.exit(1)
print("SetAVTransportURI OK (TV starts processing — Play response may even time out, that's fine)")
try:
    soap("Play",
         f'<InstanceID{DT} dt:dt="ui4">0</InstanceID><Speed dt:dt="string">1</Speed>', ctrl)
except Exception as e:
    print("(Play call note: %s)" % e)

for i in range(10):
    time.sleep(1.5)
    r = soap("GetTransportInfo", f'<InstanceID{DT} dt:dt="ui4">0</InstanceID>', ctrl)
    st = tag(r, "CurrentTransportState") or "?"
    pos = ""
    if st == "PLAYING":
        r2 = soap("GetPositionInfo", f'<InstanceID{DT} dt:dt="ui4">0</InstanceID>', ctrl)
        m2 = re.search(r"<RelTime>(.*?)</RelTime>", r2)
        pos = " @" + m2.group(1) if m2 else ""
    print(f"poll {i+1}: state={st}{pos}")
    if st in ("STOPPED", "PAUSED_PLAYBACK") and i > 1:
        break
print(f"({title} on the TV screen — verify visually)")
