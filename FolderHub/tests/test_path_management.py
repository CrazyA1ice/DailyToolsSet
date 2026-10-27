"""Safe folder path checks and explicit preview/commit migration tests."""
from pathlib import Path
import http.client
import json
import tempfile
import threading
import unittest
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
import path_management as paths


class PathManagementTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.temp = Path(t.name)
        self.store = app.Store(self.temp / 'data' / 'folderhub.db', self.temp / 'uploads')
        self.root = self.store.create({'title': '科研', 'node_type': 'root'})
        self.paper = self.store.create({'title': '论文', 'node_type': 'leaf', 'parent_id': self.root,
                                        'folder_path': 'D:\\Research\\Paper2026'})
        self.video = self.store.create({'title': '影音', 'node_type': 'leaf', 'parent_id': self.root,
                                        'folder_path': 'D:\\ResearchExtra\\Movies'})

    def get_path(self, node_id):
        return next(node['folder_path'] for node in self.store.all() if node['id'] == node_id)

    def test_prefix_exact_directory_boundary_and_case_insensitive(self):
        plan = paths.preview(self.store, 'd:/research/', 'E:/NewResearch/')
        self.assertEqual(plan['count'], 1)
        self.assertEqual(plan['changes'][0]['id'], self.paper)
        self.assertEqual(plan['changes'][0]['new_path'], 'E:\\NewResearch\\Paper2026')
        self.assertEqual(self.get_path(self.paper), 'D:\\Research\\Paper2026', 'Preview cannot write data')
        result = paths.apply(self.store, plan['source'], plan['target'], plan['fingerprint'])
        self.assertEqual(result['changed'], 1)
        self.assertEqual(self.get_path(self.paper), 'E:\\NewResearch\\Paper2026')
        self.assertEqual(self.get_path(self.video), 'D:\\ResearchExtra\\Movies')

    def test_root_drive_and_unc_prefixes(self):
        self.assertEqual(paths.normalize_prefix('D:/'), 'D:\\')
        self.assertEqual(paths.replaced_path('D:\\Movies', 'D:\\', 'E:\\'), 'E:\\Movies')
        self.assertEqual(paths.replaced_path('D:\\', 'D:\\', 'E:\\'), 'E:\\')
        self.assertEqual(paths.normalize_prefix('\\\\server\\share\\folder'), '\\\\server\\share\\folder')
        self.assertEqual(paths.replaced_path('\\\\server\\share\\old\\a',
                         '\\\\server\\share\\old', '\\\\other\\backup'), '\\\\other\\backup\\a')

    def test_invalid_prefix_and_noop_does_not_write(self):
        for p in ('', 'D:', 'D:folder', '..\\project', '\\\\server',
                  'D:\\foo\\..\\bar', '\\\\?\\C:\\Windows', '/tmp/data', 'abc'):
            with self.subTest(path=p), self.assertRaises(paths.PathRuleError):
                paths.preview(self.store, p, 'E:\\Storage')
        with self.assertRaises(paths.PathRuleError):
            paths.preview(self.store, 'D:\\Research', 'd:\\RESEARCH')
        self.assertEqual(self.get_path(self.paper), 'D:\\Research\\Paper2026')

    def test_stale_preview_cannot_overwrite_manual_changes(self):
        plan = paths.preview(self.store, 'D:\\Research', 'E:\\Research')
        self.store.update(self.paper, {'folder_path':'C:\\ManuallyMoved'})
        with self.assertRaisesRegex(paths.PathRuleError, '预览已过期'):
            paths.apply(self.store, plan['source'], plan['target'], plan['fingerprint'])
        self.assertEqual(self.get_path(self.paper), 'C:\\ManuallyMoved')

    def test_invalid_token_rolls_back_atomically(self):
        plan = paths.preview(self.store, 'D:\\', 'E:\\')
        self.assertEqual(plan['count'], 2)
        with self.assertRaises(paths.PathRuleError):
            paths.apply(self.store, plan['source'], plan['target'], '0' * 64)
        self.assertTrue(self.get_path(self.paper).startswith('D:'))
        self.assertTrue(self.get_path(self.video).startswith('D:'))

    def test_health_checks_paths_without_editing(self):
        seen = []
        result = paths.check_health(self.store, exists_fn=lambda p: seen.append(p) or p.endswith('Paper2026'))
        self.assertEqual((result['total'], result['accessible'], result['missing']), (2,1,1))
        self.assertEqual(len(seen), 2)
        self.assertEqual(self.get_path(self.paper), 'D:\\Research\\Paper2026')

    def test_no_match_is_non_mutating(self):
        plan=paths.preview(self.store, 'Z:\\Missing', 'Y:\\New')
        self.assertEqual(plan['count'], 0)
        with self.assertRaises(paths.PathRuleError):
            paths.apply(self.store, plan['source'], plan['target'], plan['fingerprint'])
        self.assertEqual(len(self.store.all()), 3)

    def test_path_health_backend_failure_is_reported(self):
        with self.assertRaises(paths.PathRuleError):
            paths.check_health(self.store, exists_fn=None) if sys.platform != 'win32' else paths.preview(self.store, 'D:bad', 'E:\\')


    def test_suggestions_rank_reachable_new_root_without_writing(self):
        extra = self.store.create({'title': '实验记录', 'node_type': 'leaf',
                                   'parent_id': self.root,
                                   'folder_path': r'D:\Research\Records'})
        existing = {r'E:\NewResearch', r'E:\NewResearch\Paper2026',
                    r'E:\NewResearch\Records'}
        calls = []
        def fake_exists(path):
            calls.append(path)
            return path in existing
        report = paths.suggest_migrations(self.store, r'E:\NewResearch', exists_fn=fake_exists)
        self.assertEqual(report['total'], 3)
        self.assertGreaterEqual(len(report['suggestions']), 1)
        best = report['suggestions'][0]
        self.assertEqual((best['source'], best['target']),
                         (r'D:\Research', r'E:\NewResearch'))
        self.assertEqual((best['linked'], best['checked'], best['verified']), (2, 2, 2))
        self.assertEqual(self.get_path(self.paper), r'D:\Research\Paper2026')
        self.assertEqual(self.get_path(extra), r'D:\Research\Records')
        self.assertLessEqual(len(calls), 1 + paths.MAX_SUGGEST_CANDIDATES * paths.MAX_SUGGEST_PROBES)
        # Choosing a proposal fills the existing preview workflow; suggestion alone cannot modify records.
        plan = paths.preview(self.store, best['source'], best['target'])
        self.assertEqual(plan['count'], 2)
        self.assertEqual(self.get_path(extra), r'D:\Research\Records')

    def test_suggestions_fail_closed_for_invalid_roots_and_empty_evidence(self):
        for target in ('', r'..\Work', r'E:relative', r'\\?\E:\Work'):
            with self.subTest(target=target), self.assertRaises(paths.PathRuleError):
                paths.suggest_migrations(self.store, target, exists_fn=lambda _: True)
        with self.assertRaisesRegex(paths.PathRuleError, '无法访问'):
            paths.suggest_migrations(self.store, r'E:\Absent', exists_fn=lambda _: False)
        report = paths.suggest_migrations(self.store, r'E:\Empty',
                                         exists_fn=lambda path: path == r'E:\Empty')
        self.assertEqual(report['suggestions'], [])
        self.assertEqual(self.get_path(self.paper), r'D:\Research\Paper2026')

    def test_suggestions_single_path_and_unc_shared_root(self):
        share = self.store.create({'title': '共享目录', 'node_type': 'leaf',
                                  'parent_id': self.root,
                                  'folder_path': r'\\oldserver\share\Team\Docs'})
        existing = {r'\\newserver\files\Projects',
                    r'\\newserver\files\Projects\Docs'}
        report = paths.suggest_migrations(self.store, r'\\newserver\files\Projects',
                                         exists_fn=lambda p: p in existing)
        matching = [s for s in report['suggestions']
                    if s['source'] == r'\\oldserver\share\Team']
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0]['verified'], 1)
        self.assertEqual(self.get_path(share), r'\\oldserver\share\Team\Docs')

    def test_suggestions_cap_directory_probes(self):
        for index in range(35):
            self.store.create({'title': f'批次 {index}', 'node_type': 'leaf',
                               'parent_id': self.root,
                               'folder_path': rf'D:\Bulk\item{index}'})
        paths_checked = []
        def fake_exists(path):
            paths_checked.append(path)
            return path == r'E:\Bulk' or path.startswith('E:\\Bulk\\item')
        report = paths.suggest_migrations(self.store, r'E:\Bulk', exists_fn=fake_exists)
        matching = [s for s in report['suggestions'] if s['source'] == r'D:\Bulk']
        self.assertEqual(len(matching), 1)
        self.assertEqual((matching[0]['linked'], matching[0]['checked'],
                          matching[0]['verified']), (35, 24, 24))
        self.assertLessEqual(len(paths_checked), 1 + paths.MAX_SUGGEST_CANDIDATES * paths.MAX_SUGGEST_PROBES)


class PathApiTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.store=app.Store(Path(temp.name)/'data'/'x.db',Path(temp.name)/'uploads')
        root=self.store.create({'title':'资料','node_type':'root'})
        self.node=self.store.create({'title':'文件','node_type':'leaf','parent_id':root,'folder_path':'D:\\Project\\File'})
        self.server=app.FolderServer(('127.0.0.1',0),self.store)
        thread=threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def request(self, path, payload=None, auth=True):
        conn=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=3)
        headers={'Host': f'127.0.0.1:{self.server.server_port}','Content-Type':'application/json'}
        if auth: headers['X-FolderHub-Token']=self.server.token
        conn.request('POST',path,body=json.dumps(payload if payload is not None else {}),headers=headers)
        resp=conn.getresponse()
        raw=resp.read()
        conn.close()
        return resp.status,json.loads(raw)

    def test_auth_required_for_diagnostics_and_writes(self):
        for endpoint in ('/api/paths/check','/api/paths/suggest','/api/paths/preview','/api/paths/apply'):
            with self.subTest(endpoint=endpoint):
                status,_=self.request(endpoint,auth=False)
                self.assertEqual(status,403)

    def test_http_preview_commit_and_expired_preview(self):
        status,plan=self.request('/api/paths/preview',{'source':'D:\\Project','target':'E:\\Project'})
        self.assertEqual(status,200)
        self.assertEqual(plan['count'],1)
        bad,result=self.request('/api/paths/apply',{'source':plan['source'],'target':plan['target'],'fingerprint':'bad'})
        self.assertEqual(bad,400)
        self.assertIn('预览',result['error'])
        ok,result=self.request('/api/paths/apply',{'source':plan['source'],'target':plan['target'],'fingerprint':plan['fingerprint']})
        self.assertEqual(ok,200)
        self.assertEqual(result['changed'],1)
        late,_=self.request('/api/paths/apply',{'source':plan['source'],'target':plan['target'],'fingerprint':plan['fingerprint']})
        self.assertEqual(late,400)

    def test_http_suggestions_are_read_only_and_token_protected(self):
        suggested = {'target': r'E:\New', 'total': 1, 'sample_limit': 24,
                     'suggestions': [{'source': r'D:\Project', 'target': r'E:\New',
                                      'linked': 1, 'checked': 1, 'verified': 1, 'examples': []}]}
        with patch.object(paths, 'suggest_migrations', return_value=suggested) as helper:
            code, payload = self.request('/api/paths/suggest', {'target': r'E:\New'})
            self.assertEqual(code, 200)
            self.assertEqual(payload, suggested)
            helper.assert_called_once_with(self.store, r'E:\New')
        with patch.object(paths, 'suggest_migrations',
                          side_effect=paths.PathRuleError('不可访问')):
            code, payload = self.request('/api/paths/suggest', {'target': r'E:\Absent'})
            self.assertEqual(code, 400)
            self.assertIn('不可访问', payload['error'])

    def test_http_health_uses_local_paths(self):
        with patch.object(paths,'check_health',return_value={'total':1,'accessible':0,'missing':1,'items':[]}) as health:
            status,data=self.request('/api/paths/check')
            self.assertEqual(status,200)
            self.assertEqual(data['missing'],1)
            health.assert_called_once_with(self.store)


if __name__ == '__main__':
    unittest.main()
