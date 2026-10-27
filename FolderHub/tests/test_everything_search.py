"""Everything bridge tests: all executable invocations are mocked, no index required."""
import os
import subprocess
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import everything_search as es


class EverythingBridgeTests(unittest.TestCase):
    def test_search_is_bounded_uses_argument_vector_and_does_not_run_shell(self):
        command=[]
        def fake(args,**kwargs):
            command.append((args,kwargs))
            return subprocess.CompletedProcess(args,0,
                "C:\\Data\\paper.pdf\nC:\\Data\\results\nC:\\Data\\paper.pdf\nrelative.txt\n","")
        with patch.object(es.os.path,"isdir",side_effect=lambda p:p.endswith("results")), \
             patch.object(es.os.path,"isfile",side_effect=lambda p:p.endswith("paper.pdf")):
            got=es.search("paper | report",run=fake,executable=r"C:\Tools\es.exe")
        self.assertEqual([n["path"] for n in got["items"]],
                         [r"C:\Data\paper.pdf",r"C:\Data\results"])
        self.assertEqual([n["kind"] for n in got["items"]],["file","folder"])
        self.assertEqual(got["limit"],30)
        args,opts=command[0]
        self.assertEqual(args[:4],[r"C:\Tools\es.exe","-n","30","-full-path"])
        self.assertEqual(args[-2:],["--","paper | report"])
        self.assertEqual(opts["timeout"],4)
        self.assertNotIn("shell",opts)

    def test_missing_index_entries_are_not_misclassified_as_files(self):
        seen=[]
        def fake(args,**kwargs):
            seen.append(args)
            return subprocess.CompletedProcess(args,0,
                "C:\\Offline\\missing_folder\n"
                "C:\\Real\\notes.pdf\n"
                "C:\\Real\\project\n","")
        with patch.object(es.os.path,"isdir",side_effect=lambda p:p.endswith("project")), \
             patch.object(es.os.path,"isfile",side_effect=lambda p:p.endswith("notes.pdf")):
            response=es.search("work",run=fake,executable="es.exe")
        self.assertEqual([(item["name"],item["kind"]) for item in response["items"]],
                         [("notes.pdf","file"),("project","folder")])
        self.assertEqual(response["unavailable"],1)
        self.assertEqual(len(seen),1)

    def test_invalid_queries_rejected_without_launching_process(self):
        for query in (None,"","a","x"*101,"test\ncmd"):
            with self.subTest(query=query):
                with patch.object(es.subprocess,"run") as runner:
                    with self.assertRaises(ValueError):
                        es.search(query,executable="es.exe")
                    runner.assert_not_called()

    def test_search_errors_are_clear_and_nonfatal(self):
        def bad(args,**kwargs):
            return subprocess.CompletedProcess(args,8,"","")
        with self.assertRaises(es.EverythingUnavailable):
            es.search("report",run=bad,executable="es.exe")
        def timeout(args,**kwargs):
            raise subprocess.TimeoutExpired(args,4)
        with self.assertRaises(es.EverythingUnavailable):
            es.search("report",run=timeout,executable="es.exe")

    def test_optional_executable_resolution_requires_real_es_filename(self):
        with patch.dict(os.environ,{"FOLDERHUB_ES_PATH":r"C:\Tools\other.exe"}):
            with self.assertRaises(es.EverythingUnavailable):
                es.find_es()
        with patch.dict(os.environ,{"FOLDERHUB_ES_PATH":""}), \
             patch.object(es.shutil,"which",return_value=None):
            with self.assertRaises(es.EverythingUnavailable):
                es.find_es()

if __name__=="__main__":
    unittest.main()
