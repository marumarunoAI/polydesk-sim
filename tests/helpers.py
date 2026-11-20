import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import common  # noqa: E402


class TempDirs:
    """把 common.DIRS 指到暫存資料夾，測試不碰真實輸出。"""

    def __enter__(self):
        self.root = tempfile.mkdtemp()
        self.old = dict(common.DIRS)
        for k in common.DIRS:
            common.DIRS[k] = os.path.join(self.root, k)
            os.makedirs(common.DIRS[k])
        return self

    def __exit__(self, *a):
        common.DIRS.clear()
        common.DIRS.update(self.old)
        shutil.rmtree(self.root)
