"""Machine-wide exclusive ToolsPD browser access; locks release after a crash."""
import os
import tempfile
import threading
from pathlib import Path

DEFAULT_NAME = 'Global\\SeoResearch.ToolsPD.Browser.v1'
_held = set()
_guard = threading.Lock()


class ToolsPDBusy(ValueError):
    def __init__(self):
        super().__init__('toolspd_access_busy: another client owns ToolsPD; the shared queue will wait')
        self.reason = 'toolspd_access_busy'


class ToolsPDAccess:
    def __init__(self, name=DEFAULT_NAME):
        self.name, self.handle, self.stream = name, None, None
        self.acquired = False

    def acquire(self):
        if self.acquired:
            return self
        with _guard:
            if self.name in _held:
                raise ToolsPDBusy()
            if os.name == 'nt':
                import ctypes
                from ctypes import wintypes
                api = ctypes.WinDLL('kernel32', use_last_error=True)
                api.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
                api.CreateMutexW.restype = wintypes.HANDLE
                api.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
                api.WaitForSingleObject.restype = wintypes.DWORD
                api.ReleaseMutex.argtypes = [wintypes.HANDLE]
                api.CloseHandle.argtypes = [wintypes.HANDLE]
                handle = api.CreateMutexW(None, False, self.name)
                if not handle:
                    raise OSError(ctypes.get_last_error(), 'Could not create ToolsPD access mutex')
                result = api.WaitForSingleObject(handle, 0)
                if result not in (0, 0x80):
                    error = ctypes.get_last_error()
                    api.CloseHandle(handle)
                    if result == 258:
                        raise ToolsPDBusy()
                    raise OSError(error, 'Could not acquire ToolsPD access mutex')
                self.api, self.handle = api, handle
            else:
                import fcntl
                import hashlib
                name = hashlib.sha256(self.name.encode()).hexdigest()
                path = Path(tempfile.gettempdir()) / ('seo-toolspd-'+str(os.getuid())+'-'+name+'.lock')
                stream = path.open('a+b')
                os.chmod(path, 0o600)
                try:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    stream.close()
                    raise ToolsPDBusy() from None
                self.stream = stream
            _held.add(self.name)
            self.acquired = True
        return self

    def close(self):
        with _guard:
            if not self.acquired:
                return
            try:
                if self.handle is not None:
                    try:
                        self.api.ReleaseMutex(self.handle)
                    finally:
                        self.api.CloseHandle(self.handle)
                    self.handle = None
                if self.stream is not None:
                    self.stream.close()
                    self.stream = None
            finally:
                self.acquired = False
                _held.discard(self.name)

    def __enter__(self):
        return self.acquire()

    def __exit__(self, *args):
        self.close()


def access_status():
    try:
        with ToolsPDAccess():
            return dict(busy=False, enforced=True, scope='application processes on this machine')
    except ToolsPDBusy:
        return dict(busy=True, enforced=True, scope='application processes on this machine')
