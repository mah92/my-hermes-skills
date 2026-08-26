#!/usr/bin/env python3
"""Control the Wanbo renderer: volume / mute / stop / pause / play / status.
Usage:
  python3 control.py status
  python3 control.py volume          # print current
  python3 control.py volume 30       # set
  python3 control.py mute            # print current
  python3 control.py mute 1|0
  python3 control.py stop|pause|play
"""
import re, socket, struct, sys, time, urllib.request, urllib.error

AV = "urn:schemas-upnp-org:service:AVTransport:1"
RC = "urn:schemas-upnp-org:service:RenderingControl:1"

def discover(endpoint_urls=False, target="192.168.1.103"):
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
    def ctrl(needle):
        m = re.search(r"<controlURL>(.*?%s.*?)</controlURL>" % needle, root, re.S)
        if not m: sys.exit("controlURL %s not found" % needle)
        cu = m.group(1).strip()
        return cu if cu.startswith("http") else loc.rstrip("/") + cu
    return ctrl("AVTransport"), (ctrl("RenderingControl") if endpoint_urls else None)

def soap(action, args, ctrl, service):
    body = (f'<?xml version="1.0" encoding="utf-8"?>'
            f'<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
            f's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
            f'<s:Body><u:{action} xmlns:u="{service}">{args}</u:{action}></s:Body></s:Envelope>')
    req = urllib.request.Request(ctrl, data=body.encode(),
                                 headers={"Content-Type": 'text/xml; charset="utf-8"',
                                          "SOAPAction": f'"{service}#{action}"'})
    try:
        return urllib.request.urlopen(req, timeout=10).read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.read().decode("utf-8", "replace")

def node(r, tag):
    m = re.search(r"<%s>(.*?)</%s>" % (tag, tag), r, re.S)
    return m.group(1).strip() if m else None

av, rc = discover(endpoint_urls=True)
cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
val = sys.argv[2] if len(sys.argv) > 2 else None

if cmd == "status":
    print("state:", node(soap("GetTransportInfo", "<InstanceID>0</InstanceID>", av, AV), "CurrentTransportState"))
    print("position:", node(soap("GetPositionInfo", "<InstanceID>0</InstanceID>", av, AV), "RelTime"))
    print("volume:", node(soap("GetVolume", "<InstanceID>0</InstanceID><Channel>Master</Channel>", rc, RC), "CurrentVolume"))
elif cmd == "volume":
    if val is None:
        print("volume:", node(soap("GetVolume", "<InstanceID>0</InstanceID><Channel>Master</Channel>", rc, RC), "CurrentVolume"))
    else:
        r = soap("SetVolume", f"<InstanceID>0</InstanceID><Channel>Master</Channel><DesiredVolume>{val}</DesiredVolume>", rc, RC)
        print("set volume ->", re.sub(r"\s+", " ", r)[:120])
elif cmd == "mute":
    if val is None:
        print("mute:", node(soap("GetMute", "<InstanceID>0</InstanceID><Channel>Master</Channel>", rc, RC), "CurrentMute"))
    else:
        r = soap("SetMute", f"<InstanceID>0</InstanceID><Channel>Master</Channel><DesiredMute>{val}</DesiredMute>", rc, RC)
        print("set mute ->", re.sub(r"\s+", " ", r)[:120])
elif cmd in ("stop", "pause", "play"):
    action = {"stop": "Stop", "pause": "Pause", "play": "Play"}[cmd]
    args = "<InstanceID>0</InstanceID>" + ("<Speed>1</Speed>" if cmd == "play" else "")
    r = soap(action, args, av, AV)
    print(f"{cmd} ->", re.sub(r"\s+", " ", r)[:120])
else:
    sys.exit("usage: status | volume [N] | mute [0|1] | stop | pause | play")
