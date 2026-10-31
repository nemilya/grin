"""Media repository laid over the work tree (engine/media.py): push, pull, pin, merge, guards. No network:
the "remote" is a bare repository in a temp folder."""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from engine import media


def sh(*args, cwd=None, input=None):
    return subprocess.run(args, cwd=cwd, input=input, check=True, capture_output=True, text=True).stdout


class MediaTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = Path(self.tmp.name)
        self.remote = t / 'remote.git'
        sh('git', 'init', '-q', '--bare', '-b', 'main', str(self.remote))
        sh('git', '--git-dir', str(self.remote), 'config', 'uploadpack.allowReachableSHA1InWant', 'true')
        self.env = {k: os.environ.get(k) for k in ('MEDIA_REMOTE', 'GIT_AUTHOR_NAME', 'GIT_AUTHOR_EMAIL',
                                                   'GIT_COMMITTER_NAME', 'GIT_COMMITTER_EMAIL', 'MEDIA_CHECK')}
        os.environ.update(MEDIA_REMOTE=str(self.remote), GIT_AUTHOR_NAME='t', GIT_AUTHOR_EMAIL='t@t',
                          GIT_COMMITTER_NAME='t', GIT_COMMITTER_EMAIL='t@t')
        os.environ.pop('MEDIA_CHECK', None)
        self.a, self.b = t / 'a', t / 'b'
        self.root0 = media.ROOT
        self.log = []

    def tearDown(self):
        media.ROOT = self.root0
        for k, v in self.env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self.tmp.cleanup()

    def at(self, root):
        media.ROOT = root
        return root

    def put(self, root, rel, data: bytes):
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def test_roundtrip_pin_and_guards(self):
        a = self.at(self.a)
        self.put(a, 'stories/s/assets/doctor/seated.webp', b'v1')
        self.put(a, 'stories/s/voicings/n/takes/story-001-1.opus', b'voice')
        self.put(a, 'stories/s/assets/takes/doctor__seated@1.webp', b'draft')   # local only
        self.put(a, 'stories/s/assets/assets.json', b'{}')                        # text: the code repo's
        self.put(a, 'stories/s/build/timeline.json', b'{}')
        self.assertEqual(media.media_files(), ['stories/s/assets/doctor/seated.webp',
                                               'stories/s/voicings/n/takes/story-001-1.opus'])
        r1 = media.push(log=self.log.append)
        self.assertEqual(media.pinned(), r1)
        self.assertEqual(sh('git', '--git-dir', str(self.remote), 'rev-parse', 'main').strip(), r1)

        # another machine: code (with media.rev) but no media → generation is refused until pulled
        b = self.at(self.b)
        (b / 'stories/s').mkdir(parents=True)
        (b / 'media.rev').write_text(r1 + '\n')
        self.assertIn('make media-pull', media.problem())
        media.pull(log=self.log.append)
        self.assertIsNone(media.problem())
        self.assertEqual((b / 'stories/s/assets/doctor/seated.webp').read_bytes(), b'v1')
        self.assertFalse((b / 'stories/s/assets/takes').exists())
        self.assertFalse(any(media.changes().values()))

        # b regenerates a picture and drops a take → a pulls the new pin
        self.put(b, 'stories/s/assets/doctor/seated.webp', b'v2')
        (b / 'stories/s/voicings/n/takes/story-001-1.opus').unlink()
        self.assertEqual(media.changes(), {'changed': ['stories/s/assets/doctor/seated.webp'], 'new': [],
                                           'deleted': ['stories/s/voicings/n/takes/story-001-1.opus']})
        r2 = media.push(log=self.log.append)
        a = self.at(self.a)
        (a / 'media.rev').write_text(r2 + '\n')
        self.assertIn('media.rev wants', media.problem())
        media.pull(log=self.log.append)
        self.assertEqual((a / 'stories/s/assets/doctor/seated.webp').read_bytes(), b'v2')
        self.assertFalse((a / 'stories/s/voicings/n/takes/story-001-1.opus').exists())
        self.assertTrue((a / 'stories/s/assets/takes/doctor__seated@1.webp').exists())

        # back to the old pin: the old picture comes back; local unpushed edits are never overwritten
        (a / 'media.rev').write_text(r1 + '\n')
        self.put(a, 'stories/s/assets/doctor/seated.webp', b'paid, not pushed')
        with self.assertRaises(media.MediaError):
            media.pull(log=self.log.append)
        media.pull(force=True, log=self.log.append)
        self.assertEqual((a / 'stories/s/assets/doctor/seated.webp').read_bytes(), b'v1')

    def test_concurrent_pushes_merge(self):
        a = self.at(self.a)
        self.put(a, 'stories/s/assets/x.webp', b'x')
        r1 = media.push(log=self.log.append)
        b = self.at(self.b)
        b.mkdir()
        (b / 'media.rev').write_text(r1 + '\n')
        media.pull(log=self.log.append)
        self.put(b, 'stories/t/assets/y.webp', b'y')
        media.push(log=self.log.append)                      # b pushes first
        a = self.at(self.a)
        self.put(a, 'stories/s/assets/z.webp', b'z')
        r3 = media.push(log=self.log.append)                 # a finds main moved → merged, nothing lost
        self.assertTrue((a / 'stories/t/assets/y.webp').exists())
        files = sh('git', '--git-dir', str(self.remote), 'ls-tree', '-r', '--name-only', 'main').split()
        self.assertEqual(sorted(files), ['stories/s/assets/x.webp', 'stories/s/assets/z.webp', 'stories/t/assets/y.webp'])
        self.assertEqual(media.pinned(), r3)

    def test_never_writes_outside_stories(self):
        a = self.at(self.a)
        self.put(a, 'stories/s/assets/x.webp', b'x')
        media.push(log=self.log.append)
        # the media repository's own README must not land in the code repository's work tree
        sh('git', '--git-dir', str(media.git_dir()), '--work-tree', str(a), 'update-index', '--add', '--cacheinfo',
           f"100644,{sh('git', '--git-dir', str(media.git_dir()), 'hash-object', '-w', '--stdin', input='media readme').strip()},README.md")
        tree = sh('git', '--git-dir', str(media.git_dir()), 'write-tree').strip()
        c = sh('git', '--git-dir', str(media.git_dir()), 'commit-tree', tree, '-p', 'HEAD', '-m', 'readme').strip()
        sh('git', '--git-dir', str(media.git_dir()), 'push', '-q', 'origin', f'{c}:refs/heads/main')
        b = self.at(self.b)
        b.mkdir()
        (b / 'README.md').write_text('code readme')
        (b / 'media.rev').write_text(c + '\n')
        media.pull(log=self.log.append)
        self.assertEqual((b / 'README.md').read_text(), 'code readme')
        self.put(b, 'stories/s/assets/w.webp', b'w')
        r = media.push(log=self.log.append)
        self.assertIn('README.md', sh('git', '--git-dir', str(self.remote), 'ls-tree', '--name-only', r).split())


if __name__ == '__main__':
    unittest.main()
