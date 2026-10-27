"""V2.3: Portable UI settings, single-import migration and ZIP backups."""
import http.client
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
from preferences_store import PreferencesStore, PreferenceError, DEFAULTS


class PortablePreferencesTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.store=app.Store(self.root/'data'/'folderhub.db',self.root/'uploads')
        self.prefs=self.store.preferences

    def test_first_browser_import_and_other_browser_cannot_overwrite(self):
        self.assertFalse(self.prefs.get()['configured'])
        result=self.prefs.save({'theme':'forest','font':'xlarge','expanded':[2,9],
                                'layout':'list'},only_if_missing=True)
        self.assertTrue(result['imported'])
        second=self.prefs.save({'theme':'midnight','expanded':[]},only_if_missing=True)
        self.assertFalse(second['imported'])
        self.assertEqual(second['settings']['theme'],'forest')
        self.assertEqual(second['settings']['expanded'],[2,9])
        self.assertTrue((self.root/'data'/'preferences.json').is_file())

    def test_survives_reopening_and_project_copy(self):
        import shutil
        self.prefs.save({'theme':'graphite','coverHeight':'tall','showCovers':False,
                         'sidebarCollapsed':True,'columns':'4','expanded':[]})
        moved=self.root/'Elsewhere'/'FolderHub'
        shutil.copytree(self.root/'data',moved/'data')
        cloned=PreferencesStore(moved/'data'/'preferences.json')
        self.assertEqual(cloned.get()['settings']['theme'],'graphite')
        self.assertEqual(cloned.get()['settings']['expanded'],[])
        self.assertFalse(cloned.get()['settings']['showCovers'])
        self.assertEqual(cloned.get()['settings']['font'],DEFAULTS['font'])

    def test_invalid_fields_do_not_modify_settings(self):
        self.prefs.save({'theme':'forest'})
        baseline=(self.root/'data'/'preferences.json').read_bytes()
        for invalid in ({'theme':'<script>'},{'font':999},{'expanded':[True]},
                        {'expanded':[1,1]},{'expanded':[-2]},
                        {'expanded':list(range(1,20002))},{'showCovers':'false'},
                        {'customDataDirectory':'C:\\Private'},[],None):
            with self.subTest(invalid=str(invalid)[:65]),self.assertRaises(PreferenceError):
                self.prefs.save(invalid)
            self.assertEqual((self.root/'data'/'preferences.json').read_bytes(),baseline)

    def test_list_density_is_portable_and_strictly_validated(self):
        self.assertEqual(self.prefs.get()['settings']['listDensity'],'normal')
        self.prefs.save({'layout':'list','listDensity':'relaxed'})
        reopened=PreferencesStore(self.root/'data'/'preferences.json')
        self.assertEqual(reopened.get()['settings']['listDensity'],'relaxed')
        snapshot=(self.root/'data'/'preferences.json').read_bytes()
        with self.assertRaises(PreferenceError):
            self.prefs.save({'listDensity':'oversized'})
        self.assertEqual((self.root/'data'/'preferences.json').read_bytes(),snapshot)

    def test_smart_views_are_portable_and_reject_invalid_changes(self):
        view={'name':'A股 + Python - 归档','includes':['A股','Python'],
              'excludes':['归档'],'mode':'all'}
        self.prefs.save({'savedViews':[view], 'theme':'forest'})
        reloaded=PreferencesStore(self.root/'data'/'preferences.json')
        self.assertEqual(reloaded.get()['settings']['savedViews'],[view])
        archive=self.store.make_portable_backup()
        try:
            with zipfile.ZipFile(archive) as zipped:
                self.assertEqual(json.loads(zipped.read('data/preferences.json'))['settings']['savedViews'],[view])
        finally:
            archive.unlink(missing_ok=True)
        before=(self.root/'data'/'preferences.json').read_bytes()
        invalid=[
            {'savedViews':None},
            {'savedViews':[{'name':'bad','includes':[],'excludes':[],'mode':'all'}]},
            {'savedViews':[{'name':'dup','includes':['A股'],'excludes':['A股'],'mode':'all'}]},
            {'savedViews':[dict(view,mode='xor')]},
            {'savedViews':[view,dict(view,name=view['name'].upper())]},
            {'savedViews':[dict(view,name='<bad>\n')]},
            {'savedViews':[dict(view,includes=['A股','a股'])]},
            {'savedViews':[view] * 25},
            {'savedViews':[dict(view,extra=True)]},
        ]
        for payload in invalid:
            with self.subTest(payload=str(payload)[:80]),self.assertRaises(PreferenceError):
                self.prefs.save(payload)
            self.assertEqual((self.root/'data'/'preferences.json').read_bytes(),before)

    def test_default_saved_views_are_not_shared_mutable_state(self):
        first=self.prefs.get()['settings']
        first['savedViews'].append({'name':'临时'})
        self.assertEqual(self.prefs.get()['settings']['savedViews'],[])
        self.assertEqual(self.prefs.snapshot_bytes().count(b'"savedViews"'),1)

    def test_workspaces_persist_in_zip_and_reject_invalid_input_atomically(self):
        valid = [
            {'name': '论文项目', 'description': '网络流量预测' + chr(10) + '实验与图表',
             'members': [3, 9, 12]},
            {'name': '开发', 'description': '', 'members': [5]},
        ]
        self.prefs.save({'workspaces': valid, 'theme': 'forest'})
        reopened = PreferencesStore(self.root / 'data' / 'preferences.json')
        self.assertEqual(reopened.get()['settings']['workspaces'], valid)
        backup = self.store.make_portable_backup()
        try:
            with zipfile.ZipFile(backup) as archive:
                data = json.loads(archive.read('data/preferences.json'))['settings']
                self.assertEqual(data['workspaces'], valid)
        finally:
            backup.unlink(missing_ok=True)

        unchanged = (self.root / 'data' / 'preferences.json').read_bytes()
        fixture = {'name': '项目', 'description': '说明', 'members': [1, 2]}
        invalid = [
            {'workspaces': None},
            {'workspaces': [dict(fixture, members=[])]},
            {'workspaces': [dict(fixture, members=[1, 1])]},
            {'workspaces': [dict(fixture, members=[True, 2])]},
            {'workspaces': [dict(fixture, members=['1'])]},
            {'workspaces': [dict(fixture, members=list(range(1, 32)))]},
            {'workspaces': [dict(fixture, name=' A ')]},
            {'workspaces': [dict(fixture, name='A' + chr(10) + 'B')]},
            {'workspaces': [dict(fixture, description='A' * 241)]},
            {'workspaces': [dict(fixture, description='A' + chr(0))]},
            {'workspaces': [fixture, dict(fixture, name='项目')]},
            {'workspaces': [fixture] * 21},
            {'workspaces': [dict(fixture, unexpected=True)]},
        ]
        for case in invalid:
            with self.subTest(case=str(case)[:80]), self.assertRaises(PreferenceError):
                self.prefs.save(case)
            self.assertEqual((self.root / 'data' / 'preferences.json').read_bytes(), unchanged)

    def test_workspace_status_and_web_resources_survive_zip(self):
        original = [{
            'name': '论文研发', 'description': '项目资源汇总', 'members': [3, 2],
            'status': 'active',
            'links': [
                {'name': '论文记录', 'url': 'https://example.org/paper?version=2#results'},
                {'name': '本地调试页', 'url': 'http://localhost:8080/docs'},
            ],
        }]
        self.prefs.save({'workspaces': original, 'theme': 'forest'})
        reopened = PreferencesStore(self.root / 'data' / 'preferences.json')
        self.assertEqual(reopened.get()['settings']['workspaces'], original)
        archive = self.store.make_portable_backup()
        try:
            with zipfile.ZipFile(archive) as zipped:
                restored = json.loads(zipped.read('data/preferences.json'))
                self.assertEqual(restored['settings']['workspaces'], original)
        finally:
            archive.unlink(missing_ok=True)

    def test_legacy_workspace_shape_stays_valid_and_untouched(self):
        legacy = [{'name': '旧科研', 'description': '不用手工升级', 'members': [6]}]
        self.prefs.save({'workspaces': legacy})
        self.assertEqual(self.prefs.get()['settings']['workspaces'], legacy)
        reopened = PreferencesStore(self.root / 'data' / 'preferences.json')
        self.assertEqual(reopened.get()['settings']['workspaces'], legacy)

    def test_workspace_resources_reject_unsafe_links_and_bad_status_atomically(self):
        good = {'name': '开发项目', 'description': '', 'members': [1],
                'status': 'planning', 'links': [{'name': '首页', 'url': 'https://example.org/'}]}
        self.prefs.save({'workspaces': [good]})
        before = (self.root / 'data' / 'preferences.json').read_bytes()
        bad_urls = [
            'javascript:alert(1)', 'file:///C:/private', 'data:text/html,hi',
            'https://user:pass@example.com/', 'https://example.com\\evil.org/',
            'https://example.com/space here', 'https://example.com/\npath',
            'https://', 'http:relative.example.com', 'https://example.com:abc/',
            'http://example.com:99999/', 'https://example.com\t',
            'https://example.com/' + ('x' * 2048),
        ]
        cases = [
            dict(good, status='invalid'),
            dict(good, status=None),
            dict(good, links=None),
            dict(good, links=[{'name': '缺失链接'}]),
            dict(good, links=[{'name': 'A', 'url': 'https://example.org/', 'extra': 1}]),
            dict(good, links=[{'name': '', 'url': 'https://example.org/'}]),
            dict(good, links=[{'name': ' A ', 'url': 'https://example.org/'}]),
            dict(good, links=[{'name': 'A' * 61, 'url': 'https://example.org/'}]),
            dict(good, links=[{'name': 'A', 'url': 'https://example.org/'}] * 9),
            dict(good, links=[{'name': 'A', 'url': 'https://example.org/'},
                              {'name': 'B', 'url': 'https://example.org/'}]),
            dict(good, extra=True),
        ]
        cases.extend(dict(good, links=[{'name': '测试', 'url': url}])
                     for url in bad_urls)
        for entry in cases:
            with self.subTest(case=str(entry)[:120]), self.assertRaises(PreferenceError):
                self.prefs.save({'workspaces': [entry]})
            self.assertEqual((self.root / 'data' / 'preferences.json').read_bytes(), before)

    def test_workspace_member_order_survives_reopen_and_backup(self):
        original = [{'name': '排序验证', 'description': '',
                     'members': [7, 3, 11, 2]}]
        self.prefs.save({'workspaces': original})
        self.assertEqual(self.prefs.get()['settings']['workspaces'][0]['members'],
                         [7, 3, 11, 2])
        reopened = PreferencesStore(self.root / 'data' / 'preferences.json')
        self.assertEqual(reopened.get()['settings']['workspaces'], original)
        archive = self.store.make_portable_backup()
        try:
            with zipfile.ZipFile(archive) as bundle:
                record = json.loads(bundle.read('data/preferences.json'))
                self.assertEqual(record['settings']['workspaces'][0]['members'],
                                 [7, 3, 11, 2])
        finally:
            archive.unlink(missing_ok=True)

    def test_workspace_defaults_are_not_shared(self):
        view = self.prefs.get()['settings']
        view['workspaces'].append({'name': '临时', 'description': '', 'members': [1]})
        self.assertEqual(self.prefs.get()['settings']['workspaces'], [])

    def test_folder_groups_survive_zip_and_validate_atomically(self):
        groups=[{'name':'量化研究','members':[11,12,13]},
                {'name':'学习资料','members':[2,7]}]
        self.prefs.save({'folderGroups':groups,'theme':'forest'})
        reopened=PreferencesStore(self.root/'data'/'preferences.json')
        self.assertEqual(reopened.get()['settings']['folderGroups'],groups)
        archive=self.store.make_portable_backup()
        try:
            with zipfile.ZipFile(archive) as zipped:
                persisted=json.loads(zipped.read('data/preferences.json'))['settings']
                self.assertEqual(persisted['folderGroups'],groups)
        finally:
            archive.unlink(missing_ok=True)
        before=(self.root/'data'/'preferences.json').read_bytes()
        invalid=[
            {'folderGroups':None},
            {'folderGroups':[{'name':'A','members':[1]}]},
            {'folderGroups':[{'name':'A','members':[1,True]}]},
            {'folderGroups':[{'name':'A','members':[1,1]}]},
            {'folderGroups':[{'name':'A','members':[1,'2']}]},
            {'folderGroups':[{'name':' A ','members':[1,2]}]},
            {'folderGroups':[{'name':'A\nB','members':[1,2]}]},
            {'folderGroups':[{'name':'A','members':list(range(1,10))}]},
            {'folderGroups':[{'name':'A','members':[1,2]},
                             {'name':'a','members':[3,4]}]},
            {'folderGroups':[{'name':'A','members':[1,2]}]*21},
            {'folderGroups':[{'name':'A','members':[1,2],'extra':True}]},
        ]
        for case in invalid:
            with self.subTest(case=str(case)[:75]),self.assertRaises(PreferenceError):
                self.prefs.save(case)
            self.assertEqual((self.root/'data'/'preferences.json').read_bytes(),before)

    def test_backup_includes_preferences_even_when_not_created(self):
        archive=self.store.make_portable_backup()
        try:
            with zipfile.ZipFile(archive) as z:
                settings=json.loads(z.read('data/preferences.json'))['settings']
                self.assertEqual(settings['theme'],'cloud')
        finally:
            archive.unlink(missing_ok=True)
        self.prefs.save({'theme':'sand','expanded':[4,12]})
        archive=self.store.make_portable_backup()
        try:
            with zipfile.ZipFile(archive) as z:
                self.assertEqual(json.loads(z.read('data/preferences.json'))['settings']['theme'],'sand')
                self.assertEqual(json.loads(z.read('data/preferences.json'))['settings']['expanded'],[4,12])
        finally:
            archive.unlink(missing_ok=True)

    def test_corrupt_configuration_does_not_get_overwritten(self):
        path=self.root/'data'/'preferences.json'
        path.write_text('invalid json',encoding='utf8')
        with self.assertRaises(PreferenceError):self.prefs.get()
        with self.assertRaises(PreferenceError):self.prefs.save({'theme':'forest'},only_if_missing=True)
        with self.assertRaises(PreferenceError):self.store.make_portable_backup()
        self.assertEqual(path.read_text(encoding='utf8'),'invalid json')
        self.assertFalse(list((self.root/'data').glob('.backup-*')))

    def test_http_preferences_write_requires_token_and_import_is_one_time(self):
        server=app.FolderServer(('127.0.0.1',0),self.store)
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        def send(method,path,payload=None,token=None,origin=None):
            connection=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
            headers={'Host':f'127.0.0.1:{server.server_port}'}
            if payload is not None:
                headers['Content-Type']='application/json'
                if token:headers['X-FolderHub-Token']=token
            if origin:headers['Origin']=origin
            connection.request(method,path,body=json.dumps(payload) if payload is not None else None,headers=headers)
            response=connection.getresponse()
            result=response.status,json.loads(response.read())
            connection.close()
            return result
        self.assertFalse(send('GET','/api/preferences')[1]['configured'])
        self.assertEqual(send('PUT','/api/preferences',{'settings':{'theme':'sand'}})[0],403)
        self.assertEqual(send('PUT','/api/preferences',{'settings':{'theme':'sand'}},server.token,'http://bad.example')[0],403)
        code,body=send('POST','/api/preferences',{'settings':{'theme':'forest','expanded':[1]}},server.token)
        self.assertEqual(code,200)
        self.assertTrue(body['imported'])
        code,body=send('POST','/api/preferences',{'settings':{'theme':'midnight'}},server.token)
        self.assertEqual(code,200)
        self.assertFalse(body['imported'])
        self.assertEqual(body['settings']['theme'],'forest')
        self.assertEqual(send('PUT','/api/preferences',{'settings':{'theme':123}},server.token)[0],400)
        self.assertEqual(send('GET','/api/preferences')[1]['settings']['theme'],'forest')
        self.assertEqual(send('PUT','/api/preferences',{'settings':{'theme':'aurora'}},server.token)[0],200)
        self.assertEqual(send('GET','/api/preferences')[1]['settings']['theme'],'aurora')


if __name__=='__main__':
    unittest.main()
