import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from playhub.core import DownloadError
from playhub.p2p import TorrentEngine


MAGNET='magnet:?xt=urn:btih:'+'a'*40


class DiscoveryTests(unittest.TestCase):
    def make_engine(self):
        engine=TorrentEngine.__new__(TorrentEngine)
        engine.lock=threading.RLock()
        engine.peer_hints={}
        return engine

    def test_explicit_peer_deduplicates_and_survives_tracker_changes(self):
        engine=self.make_engine()
        engine.add_peer_hint(MAGNET,'127.0.0.1:51413')
        engine.add_peer_hint(MAGNET+'&tr=udp%3A%2F%2Fexample.invalid%3A80%2Fannounce','127.0.0.1:51413')
        handle=Mock()
        connected=engine._connect_hints(handle,MAGNET)
        engine._connect_hints(handle,MAGNET,connected)
        handle.connect_peer.assert_called_once_with(('127.0.0.1',51413))
        self.assertEqual(len(engine.peer_hints[engine._magnet_key(MAGNET)]),1)
        other=Mock();engine._connect_hints(other,MAGNET.replace('a'*40,'b'*40))
        other.connect_peer.assert_not_called()

    def test_invalid_peer_endpoints_are_rejected_without_network(self):
        engine=self.make_engine()
        for endpoint in ('','localhost:51413','127.0.0.1:0','127.0.0.1:65536','0.0.0.0:51413','224.0.0.1:51413','http://127.0.0.1:51413','user:password@127.0.0.1:51413','127.0.0.1:51413/path','127.0.0.1:51413?token=x'):
            with self.subTest(endpoint=endpoint),self.assertRaises(DownloadError):
                engine.add_peer_hint(MAGNET,endpoint)
        self.assertEqual(engine.peer_hints,{})

    def test_ipv6_peer_endpoint(self):
        engine=self.make_engine()
        self.assertEqual(engine.add_peer_hint(MAGNET,'[::1]:51413'),('::1',51413))

    def test_lan_discovery_is_enabled_without_router_mapping(self):
        with tempfile.TemporaryDirectory() as root,patch('playhub.p2p.lt.session') as session:
            engine=TorrentEngine(Path(root)/'cache')
            settings=session.call_args.args[0]
            self.assertTrue(settings['enable_lsd'])
            self.assertFalse(settings['enable_upnp']);self.assertFalse(settings['enable_natpmp'])
            engine.close()
            TorrentEngine(Path(root)/'isolated',local_only=True)
            self.assertFalse(session.call_args.args[0]['enable_lsd'])
            self.assertFalse(session.call_args.args[0]['enable_dht'])


if __name__=='__main__':unittest.main(verbosity=2)
