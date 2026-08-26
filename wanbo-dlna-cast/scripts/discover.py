#!/usr/bin/env python3
"""Discover UPnP MediaRenderer(s) on the LAN and print AVTransport controlURLs.
Usage: python3 discover.py [target_ip]   (prints all renderers if no target)
The Wanbo's HTTP port is dynamic, so discovery must run every session.
"""
import re, socket, struct, sys, time, urllib.request

TARGET = sys.argv[1] if len(sys.argv) > 1 else None

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
s.settimeout(1.0)

locs = {}
end = time.time() + 6
while time.time() < end:
    try:
        data, addr = s.recvfrom(8192)
    except socket.timeout:
        continue
    txt = data.decode("utf-8", "replace")
    for line in txt.split("\r\n"):
        if line.lower().startswith("location:"):
            loc = line.split(":", 1)[1].strip()
            if TARGET is None or addr[0] == TARGET:
                locs[addr[0]] = loc

# Unicast fallback: some renderers (e.g. LG webOS) ignore multicast SSDP
# but answer an M-SEARCH sent directly to their IP:1900.
if TARGET and TARGET not in locs:
    us = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    us.settimeout(3.0)
    packets = ("M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\n"
               "MAN: \"ssdp:discover\"\r\nMX: 2\r\n"
               "ST: urn:schemas-upnp-org:device:MediaRenderer:1\r\n\r\n").encode()
    for _ in range(3):
        try:
            us.sendto(packets, (TARGET, 1900))
        except OSError:
            break
        try:
            data, _ = us.recvfrom(8192)
            for line in data.decode("utf-8", "replace").split("\r\n"):
                if line.lower().startswith("location:"):
                    locs[TARGET] = line.split(":", 1)[1].strip()
            if TARGET in locs:
                break
        except socket.timeout:
            pass
    us.close()

if not locs:
    print("NO MediaRenderer RESPONSES — is the projector ON and on this subnet?")
    sys.exit(1)

for ip, loc in sorted(locs.items()):
    print(f"{ip}  LOCATION: {loc}")
    try:
        root = urllib.request.urlopen(urllib.request.Request(
            loc, headers={"User-Agent": "Hermes/1.0"}), timeout=8
        ).read().decode("utf-8", "replace")
        fn = re.search(r"<friendlyName>(.*?)</friendlyName>", root, re.S)
        if fn: print(f"    friendlyName: {fn.group(1).strip()}")
        m = re.search(r"<controlURL>(.*?AVTransport.*?)</controlURL>", root, re.S)
        if m:
            cu = m.group(1).strip()
            print(f"    AVTransport control: "
                  f"{cu if cu.startswith('http') else loc.rstrip('/') + cu}")
    except Exception as e:
        print(f"    (description fetch failed: {e})")
