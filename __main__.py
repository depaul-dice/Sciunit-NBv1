import os
import ast
import subprocess
import uuid
import json
import hashlib
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

class SciunitKernel(IPythonKernel):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        implementation = super().implementation + ' sciunit'

        self.project_file = os.path.join(SCIUNIT_HOME, '.activated')

        if (os.path.exists(self.project_file)):
            self.project = open(self.project_file).read().strip()
            self.project_name = os.path.basename(os.path.normpath(self.project))
            if (os.path.exists(os.path.join(self.project, 'kernel'))):
                self.recording = False
                self.hashes = json.loads(open(os.path.join(self.project, 'kernel')).read())
            else:
                self.recording = True
                self.hashes = []

        else:
            self.project_name = 'Project_' + str(uuid.uuid4())
            self.project = os.path.join(SCIUNIT_HOME, self.project_name)
            subprocess.run(['sciunit', 'create', self.project_name])
            self.recording = True
            self.hashes = []

        self.eid = 1
        self.file = os.path.join(self.project, 'run.py')
        self.valid = True

    def do_execute(self, code, silent, store_history=True, user_expressions=None, allow_stdin=False):
        if self.valid:
            with open(self.file[1], 'a') as file:
                safe_code = make_except_safe(code)
                if safe_code:
                    if self.recording:
                        print('Recording e{}'.format(self.eid))
                        open(self.file, 'a').write(safe_code)
                        subprocess.Popen(['sciunit', 'exec', 'python3', self.file], stdout=subprocess.PIPE).communicate()

                        self.hashes.append(hashlib.sha256(safe_code.encode()).hexdigest())
                        open(os.path.join(self.project, 'kernel'), 'w').write(json.dumps(self.hashes))
                    else:
                        if (hashlib.sha256(safe_code.encode()).hexdigest() != self.hashes[self.eid - 1]):
                            print('Invalid, stopped repeating')
                            self.valid = False
                        else:
                            print('Valid, repeating e{}'.format(self.eid))
                            subprocess.Popen(['sciunit', 'repeat', 'e{}'.format(self.eid)], stdout=subprocess.PIPE).communicate()

                    self.eid += 1

        return super().do_execute(code, silent, store_history, user_expressions, allow_stdin)

if __name__ == '__main__':
    from ipykernel.kernelapp import IPKernelApp
    IPKernelApp.launch_instance(kernel_class=SciunitKernel)
