"""Integração HTTP local: motor real, autenticação e isolamento da rede."""
from __future__ import annotations
import json
import re
import sys
from pathlib import Path
from threading import Thread
from urllib.request import urlopen,Request
from urllib.error import HTTPError
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from poe_truss.server import run_server

class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=run_server(ROOT,False)
        cls.thread=Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()
        cls.origin=f'http://127.0.0.1:{cls.server.server_port}'
        with urlopen(Request(cls.origin+'/bootstrap.js',headers={'Referer':cls.origin+'/'})) as r:
            script=r.read().decode()
        cls.token=re.search(r'POE_TOKEN="([^"]+)"',script).group(1)
        with urlopen(cls.origin+'/api/default') as r:
            cls.default=json.load(r)
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join(1)

    def test_loopback_only(self):
        self.assertEqual(self.server.server_address[0],'127.0.0.1')

    def test_http_get_project(self):
        self.assertEqual(self.default['schema'],'poe-truss-python/v1')

    def test_analyze_real_http(self):
        body=json.dumps(self.default).encode()
        req=Request(self.origin+'/api/analyze',data=body,headers={
            'X-POE-Token':self.token,'Content-Type':'application/json'},method='POST')
        with urlopen(req) as r:payload=json.load(r)
        self.assertEqual(len(payload['model']['members']),65)
        self.assertIn('S_GRAV',payload['analyses'])

    def test_search_endpoint(self):
        req=Request(self.origin+'/api/suggest',data=json.dumps({'project':self.default,'options':{}}).encode(),
            headers={'X-POE-Token':self.token,'Content-Type':'application/json'},method='POST')
        with urlopen(req,timeout=30) as r:payload=json.load(r)
        self.assertGreater(payload['evaluated'],10)
        self.assertTrue(payload['candidates'])

    def test_v03_audit_export_endpoint(self):
        req=Request(self.origin+'/api/export',data=json.dumps({
            'project':self.default,'kind':'load_audit','analysis_id':'G2'}).encode(),headers={
            'X-POE-Token':self.token,'Content-Type':'application/json'},method='POST')
        with urlopen(req) as response:payload=json.load(response)
        self.assertIn('member_id',payload['data'])
        self.assertIn('case_id',payload['data'])

    def test_v03_stability_export_endpoint(self):
        req=Request(self.origin+'/api/export',data=json.dumps({
            'project':self.default,'kind':'stability'}).encode(),headers={
            'X-POE-Token':self.token,'Content-Type':'application/json'},method='POST')
        with urlopen(req) as response:payload=json.load(response)
        self.assertIn('unbraced_out_of_plane_mm',payload['data'])
        self.assertIn('resistance_verified',payload['data'])

    def test_post_without_token_forbidden(self):
        req=Request(self.origin+'/api/analyze',data=b'{}',headers={'Content-Type':'application/json'},method='POST')
        with self.assertRaises(HTTPError) as c:urlopen(req)
        self.assertEqual(c.exception.code,403)

    def test_bootstrap_without_referer_forbidden(self):
        with self.assertRaises(HTTPError) as c:urlopen(self.origin+'/bootstrap.js')
        self.assertEqual(c.exception.code,403)

    def test_origin_mismatch_forbidden(self):
        req=Request(self.origin+'/api/analyze',data=b'{}',headers={
            'X-POE-Token':self.token,'Origin':'https://example.net',
            'Content-Type':'application/json'},method='POST')
        with self.assertRaises(HTTPError) as c:urlopen(req)
        self.assertEqual(c.exception.code,403)
