#!/usr/bin/env python3
"""Cast a video file/URL to the Wanbo (UPnP MediaRenderer) and verify playback.
Usage:
  python3 cast.py <file.mp4|http://host/...> ["Title"]
Requires scripts/range_server.py already running (Range support mandatory).
"""
import os, re, socket, struct, subprocess, sys, time, urllib.request, urllib.error

AV = "urn:schemas-upnp-org:service:AVTransport:1"

def own_ip():
    try:
        out = subprocess.check_output(["hostname", "-I"]).decode().split()
        for ip in out:
            if ip.startswith("192.168."):
                return ip
    except Exception:
        pass
    return "192.168.1.108"

def discover_ctrl(target="192.168.1.103"):
    MSG = ("M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\n"
           "MAN: \"ssdp:discover\"\r\nMX: 2\r\n"
           "ST: urn:schemas-upnp-org:device:MediaRenderer:1\r\n\r\n").encode()
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("", 1900))
    mreq = struct.pack("4sl", socket.inet_aton("239.255.255.250"), socket.INADDR_ANY)
    s.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
    s.settimeout(3.0)
    for _ in range(3):
        s.sendto(MSG, ("239.255.255.250", 1900)); time.sleep(0.5)
    s.settimeout(1.0); loc = None
    end = time.time() + 6
    while time.time() < end:
        try:
            data, addr = s.recvfrom(8192)
        except socket.timeout:
            continue
        if addr[0] != target: continue
        for line in data.decode("utf-8", "replace").split("\r\n"):
            if line.lower().startswith("location:"):
                loc = line.split(":", 1)[1].strip()
    if not loc:
        sys.exit("Wanbo (SSDP) not answering on %s — is it ON?" % target)
    root = urllib.request.urlopen(loc, timeout=8).read().decode("utf-8", "replace")
    m = re.search(r"<controlURL>(.*?AVTransport.*?)</controlURL>", root, re.S)
    if not m: sys.exit("AVTransport controlURL not found in description")
    cu = m.group(1).strip()
    return cu if cu.startswith("http") else loc.rstrip("/") + cu

def soap(action, args, ctrl):
    body = (f'<?xml version="1.0" encoding="utf-8"?>'
            f'<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
            f's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
            f'<s:Body><u:{action} xmlns:u="{AV}">{args}</u:{action}></s:Body></s:Envelope>')
    req = urllib.request.Request(ctrl, data=body.encode(),
                                 headers={"Content-Type": 'text/xml; charset="utf-8"',
                                          "SOAPAction": f'"{AV}#{action}"'})
    try:
        return urllib.request.urlopen(req, timeout=10).read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.read().decode("utf-8", "replace")

if len(sys.argv) < 2:
    sys.exit(__doc__)
media, title = sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "Media"

if not media.startswith("http"):
    src = media
    media = "http://%s:8000/%s" % (own_ip(), os.path.basename(src))
    print("serving file as:", media)
    try:
        urllib.request.urlopen(media, timeout=4)
        print("media url reachable:")
    except urllib.error.HTTPError as e:
        if e.code != 404: raise
    except Exception as e:
        sys.exit("media url not reachable — is scripts/range_server.py running? (%s)" % e)
else:
    try:
        urllib.request.urlopen(media, timeout=8)
        print("media url reachable:", media)
    except Exception as e:
        sys.exit("media url not reachable: %s" % e)

ctrl = discover_ctrl()
print("controlURL:", ctrl)

didl = ('<DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/">'
        '<item id="0" parentID="-1" restricted="1">'
        '<dc:title>%s</dc:title>'
        '<res protocolInfo="http-get:*:video/mp4:*">%s</res>'
        '</item></DIDL-Lite>' % (title, media))

r = soap("SetAVTransportURI",
         f"<InstanceID>0</InstanceID><CurrentURI>{media}</CurrentURI>"
         f"<CurrentURIMetaData>{didl}</CurrentURIMetaData>", ctrl)
print("SetAVTransportURI ->", re.sub(r"\s+", " ", r)[:120])

r = soap("Play", "<InstanceID>0</InstanceID><Speed>1</Speed>", ctrl)
print("Play ->", re.sub(r"\s+", " ", r)[:120])

for i in range(10):
    time.sleep(1.0)
    r = soap("GetTransportInfo", "<InstanceID>0</InstanceID>", ctrl)
    st = re.search(r"<CurrentTransportState>(.*?)</CurrentTransportState>", r)
    st = st.group(1) if st else "?"
    pos = ""
    if st == "PLAYING":
        rr = soap("GetPositionInfo", "<InstanceID>0</InstanceID>", ctrl)
        m = re.search(r"<RelTime>(.*?)</RelTime>", rr)
        pos = " @ " + m.group(1) if m else ""
    print(f"poll {i+1}: state={st}{pos}")
    if st in ("STOPPED", "PAUSED_PLAYBACK") and i > 0:
        break
print("(" + title + " — check the projector screen)")
