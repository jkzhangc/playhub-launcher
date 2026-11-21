"""Public shortlist from ngosang/trackerslist, matching UDP connect replies
on the build network on 2026-11-20. This is not a reachability guarantee.
"""

PUBLIC_TRACKERS = (
    'udp://tracker.opentrackr.org:1337/announce',
    'udp://open.stealth.si:80/announce',
    'udp://tracker.torrent.eu.org:451/announce',
    'udp://open.demonii.com:1337/announce',
    'udp://tracker.qu.ax:6969/announce',
    'udp://tracker-udp.gbitt.info:80/announce',
    'udp://tracker.ducks.party:1984/announce',
    'udp://tracker.corpscorp.online:80/announce',
    'udp://tracker.bittor.pw:1337/announce',
    'udp://tracker.nyaa.vc:6969/announce',
    'udp://tracker.gmi.gd:6969/announce',
    'udp://explodie.org:6969/announce',
)

def merge_trackers(original=(), *, include_builtins=True):
    return list(dict.fromkeys((*original, *(PUBLIC_TRACKERS if include_builtins else ()))))
