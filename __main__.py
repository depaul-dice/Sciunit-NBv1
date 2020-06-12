import os
import ast
import subprocess
import uuid
import json
import hashlib
import socket
import psutil
from ipykernel.ipkernel import IPythonKernel

def make_except_safe(code):
    code = code.replace('\n', '\n ')
    code = 'try:\n ' + code
    code = code + '\nexcept: pass\n'
    try:
        ast.parse(code)
        return code
    except:
        return ''

SCIUNIT_HOME = os.path.expanduser('~/sciunit/')
SCIUNIT_PROJECT_FILE = os.path.join(SCIUNIT_HOME, '.activated')
SCIUNIT_SOCKET_FILE = os.path.join(SCIUNIT_HOME, 'listener.socket')

class SciunitKernel(IPythonKernel):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        implementation = super().implementation + ' sciunit'

        if (os.path.exists(SCIUNIT_PROJECT_FILE)):
            self.project = open(SCIUNIT_PROJECT_FILE).read().strip()
            self.project_name = os.path.basename(os.path.normpath(self.project))
            if (os.path.exists(os.path.join(self.project, 'kernel'))):
                self.recording = False
            else:
                self.recording = True
                open(os.path.join(self.project, 'kernel'), 'w').write(json.dumps([]))

        else:
            self.project_name = 'Project_' + str(uuid.uuid4())
            self.project = os.path.join(SCIUNIT_HOME, self.project_name)
            subprocess.run(['sciunit', 'create', self.project_name])
            self.recording = True
            open(os.path.join(self.project, 'kernel'), 'w').write(json.dumps([]))

        self.eid = 1
        self.file = os.path.join(self.project, 'run.py')
        self.valid = True

        files = psutil.Process().open_files()
        for file in files:
            os.close(file.fd)

        criu_path = os.path.join(self.project, 'criu0')
        data = ['Dump', os.getpid(), os.getppid(), criu_path, 0]
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.connect(SCIUNIT_SOCKET_FILE)
        client.sendall(json.dumps(data).encode())
        client.close()

    def do_execute(self, code, silent, store_history=True, user_expressions=None, allow_stdin=False):
        criu_path = os.path.join(self.project, f'criu{self.eid}')
        if (os.path.exists(criu_path)): self.recording = False
        hashes = json.loads(open(os.path.join(self.project, 'kernel')).read())
        if not self.recording and (len(hashes) == self.eid - 1): self.valid = False
    
        data = []
        if self.valid:
            with open(self.file[1], 'a') as file:
                safe_code = make_except_safe(code)
                if safe_code:
                    if self.recording:
                        print('Recording e{}'.format(self.eid))
                        open(self.file, 'a').write(safe_code)
                        subprocess.Popen(['sciunit', 'exec', 'python3', self.file], stdout=subprocess.PIPE).communicate()

                        hashes.append(hashlib.sha256(safe_code.encode()).hexdigest())
                        open(os.path.join(self.project, 'kernel'), 'w').write(json.dumps(hashes))

                        data = ['Dump', os.getpid(), os.getppid(), criu_path, self.eid]
                    else:
                        if (hashlib.sha256(safe_code.encode()).hexdigest() != hashes[self.eid - 1]):
                            print('Invalid, stopped repeating')
                            self.valid = False
                        else:
                            print('Valid, repeating e{}'.format(self.eid))
                            subprocess.Popen(['sciunit', 'repeat', 'e{}'.format(self.eid)], stdout=subprocess.PIPE).communicate()
                            data = ['Restore', os.getpid(), os.getppid(), criu_path, self.eid]

                    self.eid += 1

        output = super().do_execute(code, silent, False, user_expressions, allow_stdin)

        if data:
            client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            client.connect(SCIUNIT_SOCKET_FILE)
            client.sendall(json.dumps(data).encode())
            client.close()
            # TODO: Wait without Socket
        
        return output

if __name__ == '__main__':
    from ipykernel.kernelapp import IPKernelApp
    IPKernelApp.launch_instance(kernel_class=SciunitKernel)
