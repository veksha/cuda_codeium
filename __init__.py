#import sys
#sys.stdout = sys.__stdout__
#sys.stderr = sys.__stderr__

import sys
import os
import json
import gzip
import io
import queue
import subprocess
from threading import Thread
import requests
import shutil
import traceback
import time
import tempfile
from concurrent.futures import ThreadPoolExecutor
from collections import namedtuple

from cudatext import *
import cudax_lib as apx
import cudatext_cmd as cmds

PLUGIN_NAME = 'cuda_codeium'
LOG = False

IS_WIN = os.name=='nt'
_MAXLINE = 65536

API_URL = 'https://server.codeium.com'
HEADERS = {'Content-Type': 'application/json'}
SNIP_ID = PLUGIN_NAME+'__snip'

if sys.platform == 'linux' and 'arm' in sys.version.lower():
    BIN_SUFFIX = 'linux_arm'
elif sys.platform == 'linux':
    BIN_SUFFIX = 'linux_x64'
elif sys.platform == 'darwin' and 'arm' in sys.version.lower():
    BIN_SUFFIX = 'macos_arm'
elif sys.platform == 'darwin':
    BIN_SUFFIX = 'macos_x64'
else:
    BIN_SUFFIX = 'windows_x64.exe'

fn_config = os.path.join(app_path(APP_DIR_SETTINGS), PLUGIN_NAME+'.ini')
option_token = ''
option_api_key = ''


Item = namedtuple('Item', 'hint text suffix text_inline text_inline_mask text_block start_position end_position cursor_offset')

class Command:
    
    def __init__(self):
        self.name = 'codeium'
        self.port = None
        self.token = None
        self.api_key = None
        self.language_server_version = '1.2.15'
        self.manager_dir = None
        self.text = '# print hello world in nim language\n'
        self.row = 1
        self.col = 0
        self.process = None
        
        global option_token
        global option_api_key
        option_token = ini_read(fn_config, 'op', 'token', option_token)
        option_api_key = ini_read(fn_config, 'op', 'api_key', option_api_key)
        self.token = option_token
        self.api_key = option_api_key
        
    def get_token(self):
        url = 'https://www.codeium.com/profile?response_type=token&redirect_uri=vim-show-auth-token&state=a&scope=openid+profile+email&redirect_parameters_type=query'
        apx.safe_open_url(url)
        self.token = dlg_input('Your token: ', '')
        
        # save token to .ini
        global option_token
        option_token = self.token
        ini_write(fn_config, 'op', 'token', option_token)
        
        self.log_in()
        
    def register_user(self, token):
        #url = 'https://api.codeium.com/register_user/'
        url = API_URL + '/exa.api_server_pb.ApiServerService/RegisterUser'
        data = '{{"firebase_id_token": "{}"}}'.format(token)
        
        try:
            response = requests.post(url, headers=HEADERS, data=data, timeout=4)
            #response.raise_for_status()
        except requests.exceptions.Timeout:
            pass;      LOG and print("ERROR: Can't get API key: The request timed out.")
            return
        except requests.exceptions.RequestException as e:
            pass;      LOG and print("ERROR: Can't get API key. Error:", e)
            return
        result = response.content
        result_str = result.decode('utf-8')
        result_json = json.loads(result_str)
        
        api_key = result_json.get('api_key', None)
        if api_key is None:
            pass;      LOG and print("ERROR: Can't get API key..")
            return
        
        pass;    LOG and print("got api_key:", api_key)
        return api_key
        
    def download_server(self, out_file):
        url = "https://github.com/Exafunction/codeium/releases/download/language-server-v{}/language_server_{}.gz".format(
            self.language_server_version,
            BIN_SUFFIX
        )
        
        msg_status('{}: Downloading server...'.format(self.name))
        app_idle()
        response = requests.get(url)
        
        if response.status_code == 200:
            buffer = io.BytesIO(response.content)
            
            with gzip.GzipFile(fileobj=buffer, mode="rb") as gz_file:
                with open(out_file, "wb") as f_out:
                    shutil.copyfileobj(gz_file, f_out)            
            
            pass;    LOG and print("Codeium lang server downloaded!")
        else:
            print("ERROR: Cannot download Codeium lang server: {} - {}".format(response.status_code, response.reason))
            return
        
    def get_executable(self):
        data_dir = app_path(APP_DIR_DATA)
        codeium_dir = os.path.join(data_dir, PLUGIN_NAME)
        os.makedirs(codeium_dir, exist_ok=True)
        
        executable = os.path.join(codeium_dir,'language_server_'+BIN_SUFFIX)
        return executable
        
    def log_in(self):
        if self.process is not None:
            self.find_port()
            return
        
        msg_status('{}: Starting...'.format(self.name))
        
        if self.token is None:
            self.get_token()
        
        if not self.api_key:
            with ThreadPoolExecutor() as ex:
                future = ex.submit(self.register_user, self.token)
                while not future.done():
                    app_idle()
                    time.sleep(0.001)
                self.api_key = future.result()
            
            if not self.api_key:
                print("ERROR: {}: Can't register user. Maybe token has expired. Try getting new token.".format(self.name))
                return
        
        # save api_key to .ini
        global option_api_key
        option_api_key = self.api_key
        ini_write(fn_config, 'op', 'api_key', option_api_key)

        self.manager_dir = tempfile.mkdtemp(prefix=self.name+'_')
        self.executable = self.get_executable()
        
        if not os.path.exists(self.executable):
            self.download_server(self.executable)
        
        self.run_server(self.executable, self.manager_dir)
        
    def run_server(self, executable, manager_dir):
        if not IS_WIN:
            os.chmod(executable, 0o755)
        args = [
            executable,
            '--api_server_url', API_URL,
            '--manager_dir', manager_dir,
        ]
        startupinfo = None
        if IS_WIN:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        self.process = subprocess.Popen(args, startupinfo=startupinfo)
        
        def wait_for_port_file():
            self.port = None
            while self.port is None:
                self.find_port()
                time.sleep(0.3)
                
        with ThreadPoolExecutor() as ex:
            future = ex.submit(wait_for_port_file)
            while not future.done():
                app_idle()
                time.sleep(0.001)
        
    def find_port(self, tag=''):
        import re
        files = os.listdir(self.manager_dir)
        num_files = [f for f in files if re.match(r'^\d+$', f)]
        if num_files:
            self.port = int(num_files[0])
            pass;    LOG and print("Found port:", self.port)
            timer_proc(TIMER_START, self.heartbeat, 5000)
            msg_status("{}: Logged in".format(self.name))
            
    def get_completions(self):
        if self.port is None:
            self.log_in()
            
        with ThreadPoolExecutor() as ex:
            future = ex.submit(self.request_completions)
            while not future.done():
                app_idle()
                time.sleep(0.001)
            items = future.result()
            
            if items is None:
                return
            
            msg_status("{}: Got {} items".format(self.name, len(items)))
            
            ## debug
            #ed.cmd(cmds.cmd_FileNew)
            #ed.insert(0, 0, str(items))
            
            completions = []
            for comp in items:
                text = comp['completion']['text']
                text_inline = ''
                text_inline_mask = ''
                text_block = ''
                inline_num = 1
                parts = comp.get('completionParts', [])
                for part in parts:
                    if part['type'] == 'COMPLETION_PART_TYPE_INLINE':
                        if inline_num == 1:
                            text_inline = part['text']
                        else:
                            text_inline += part.get('prefix', '') + part['text']
                        inline_num += 1
                    elif part['type'] == 'COMPLETION_PART_TYPE_INLINE_MASK':
                        text_inline_mask = part['text']
                    elif part['type'] == 'COMPLETION_PART_TYPE_BLOCK':
                        text_block = part['text']
                        
                #if inline_num > 1:
                    #print("ERROR: inline_num=", inline_num)
                
                start_position = comp['range']['startPosition']
                end_position   = comp['range']['endPosition']
                start_position = (int(start_position.get('col', 0)), int(start_position.get('row', 0)))
                end_position   = (int(end_position.get('col', 0)), int(end_position.get('row', 0)))
                
                suffix = comp.get('suffix', None)
                cursor_offset = int(suffix.get('deltaCursorOffset', 0)) if suffix else 0
                suffix = suffix['text'] if suffix else ''
                
                if text_inline:
                    hint = text_inline.replace('\n',' ') + ' ' + text_block.replace('\n',' ')
                else:
                    hint = text.replace('\n',' ')
                
                completions.append(Item(
                    hint,
                    text,
                    suffix,
                    text_inline,
                    text_inline_mask,
                    text_block,
                    start_position,
                    end_position,
                    cursor_offset,
                ))
            
            self.completions = completions
            
            words = ['{}\t{}\t{}|{}'.format(
                        item.hint,
                        '',
                        '', i)
                        for i,item in enumerate(completions)
                    ]
            
            ed.complete_alt('\n'.join(words), SNIP_ID, len_chars=0)

    def on_snippet(self, ed_self: Editor, snippet_id, snippet_text):
        if snippet_id != SNIP_ID or '|' not in snippet_text:
            return
        _, item_ind = snippet_text.split('|')
        item_ind = int(item_ind)
        
        item = self.completions[item_ind]
        
        new_caret = ed_self.replace(
            item.start_position[0],
            item.start_position[1],
            item.end_position[0],
            item.end_position[1],
            item.text + item.suffix
        )
        
        if item.cursor_offset:
            offset = ed_self.convert(CONVERT_CARET_TO_OFFSET, new_caret[0], new_caret[1])
            offset += item.cursor_offset
            new_caret = ed_self.convert(CONVERT_OFFSET_TO_CARET, offset, 0)
            new_caret = (new_caret[0], new_caret[1], -1, -1)
        
        ed_self.set_caret(*new_caret)

        
    def heartbeat(self, *args):
        def _heartbeat_request():
            url = 'http://127.0.0.1:{}/exa.language_server_pb.LanguageServerService/Heartbeat'.format(
                self.port
            )
            
            data = {
                'metadata': {
                    'api_key': self.api_key,
                    'ide_name': 'vscode',
                    'ide_version': '1.77.3',
                    'extension_version': self.language_server_version,
                    }
            }
            
            try:
                response = requests.post(url, headers=HEADERS, data=json.dumps(data), timeout=4)
                response.raise_for_status()
            except requests.exceptions.Timeout:
                print("ERROR: Heartbeat failed: The request timed out.")
                return
            except requests.exceptions.RequestException as e:
                print("ERROR: Heartbeat failed. Error:", e)
                return
            
            result = response.content
            
            result_str = result.decode('utf-8')
            return result_str
        
        with ThreadPoolExecutor() as ex:
            future = ex.submit(_heartbeat_request)
            while not future.done():
                app_idle()
                time.sleep(0.001)
    
    def request_completions(self, *args):
        if self.port is None:
            print("ERROR: Can't get completions: server is not started.")
            return
        
        url = 'http://127.0.0.1:{}/exa.language_server_pb.LanguageServerService/GetCompletions'.format(
            self.port
        )
        
        self.text = ed.get_text_all()
        self.col, self.row = ed.get_carets()[0][:2]
        
        lexer = ed.get_prop(PROP_LEXER_FILE)
        lang =  language_enum.get(lex_ids.get(lexer,''), 0)
        
        data = {
            'metadata': {
                'api_key': self.api_key,
                'ide_name': 'vscode',
                'ide_version': '1.77.3',
                'extension_version': self.language_server_version,
                },
            'document': {
                'text': self.text,
                'editor_language': lexer,
                'language': lang,
                'cursor_position': {
                    'row': self.row,
                    'col': self.col,
                },
                #'absolute_path': '',
                #'relative_path': '',
            },
            'editor_options': {
                'tab_size': ed.get_prop(PROP_TAB_SIZE),
                'insert_spaces': ed.get_prop(PROP_TAB_SPACES),
            },
            #'other_documents': {},
        }
        try:
            response = requests.post(url, headers=HEADERS, data=json.dumps(data), timeout=4)
            response.raise_for_status()
        except requests.exceptions.Timeout:
            print("ERROR: Can't get completions: The request timed out")
            return
        except requests.exceptions.RequestException as e:
            print("ERROR: Can't get completions. Error:", e)
            return
        result = response.content
        
        result_str = result.decode('utf-8')
        result_json = json.loads(result_str)
        
        #print("get_completions:", result_json)
        
        #print("message: ", result_json['state'])
        items = result_json.get('completionItems', [])
        return items
        
    def shutdown(self, *args, **vargs):
        pass;       LOG and print('{}: shutting down'.format(self.name))
        
        if self.process:
            if IS_WIN:
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                subprocess.call(['taskkill', '/F', '/T', '/PID',  str(self.process.pid)], startupinfo=startupinfo)
            else:
                self.process.terminate()
                self.process.wait()
            self.process = None


    def on_exit(self, *args, **vargs):
        self.shutdown()


language_enum = {
    'unspecified': 0,
    'c': 1,
    'clojure': 2,
    'coffeescript': 3,
    'cpp': 4,
    'csharp': 5,
    'css': 6,
    'cudacpp': 7,
    'dockerfile': 8,
    'go': 9,
    'groovy': 10,
    'handlebars': 11,
    'haskell': 12,
    'hcl': 13,
    'html': 14,
    'ini': 15,
    'java': 16,
    'javascript': 17,
    'json': 18,
    'julia': 19,
    'kotlin': 20,
    'latex': 21,
    'less': 22,
    'lua': 23,
    'makefile': 24,
    'markdown': 25,
    'objectivec': 26,
    'objectivecpp': 27,
    'perl': 28,
    'php': 29,
    'plaintext': 30,
    'protobuf': 31,
    'pbtxt': 32,
    'python': 33,
    'r': 34,
    'ruby': 35,
    'rust': 36,
    'sass': 37,
    'scala': 38,
    'scss': 39,
    'shell': 40,
    'sql': 41,
    'starlark': 42,
    'swift': 43,
    'typescriptreact': 44,
    'typescript': 45,
    'visualbasic': 46,
    'vue': 47,
    'xml': 48,
    'xsl': 49,
    'yaml': 50,
    'svelte': 51,
}

# taken from LSP plugin
lex_ids = {
    'ABAP': 'abap',
    'Batch files': 'bat', # spec: 'Windows Bat'
    'BibTeX': 'bibtex',
    'Clojure': 'clojure',
    'CoffeeScript': 'coffeescript', # spec: 'Coffeescript'
    'C': 'c',
    'C++': 'cpp',
    'C#': 'csharp',
    'CSS': 'css',
    'Diff': 'diff',
    'Dart': 'dart',
    'Dockerfile': 'dockerfile',
    'Elixir': 'elixir',
    'Erlang': 'erlang',
    'F#': 'fsharp',
    #'Git': 'git-commit and git-rebase', #TODO
    'Go': 'go',
    'Groovy': 'groovy',
    'HTML Handlebars': 'handlebars', # spec: 'Handlebars'
    'HTML': 'html',
    'Ini files': 'ini', # spec: 'Ini'
    'Java': 'java',
    'JavaScript': 'javascript',
    #'JavaScript React': 'javascriptreact', # Not in CudaText
    'JSON': 'json',
    'LaTeX': 'latex',
    'LESS': 'less', # spec: 'Less'
    'Lua': 'lua',
    'Makefile': 'makefile',
    'Markdown': 'markdown',
    'Objective-C': 'objective-c',
    #'Objective-C++': 'objective-cpp', # Not in CudaText
    'Perl': 'perl',
    #'Perl 6': 'perl6', # Not in CudaText
    'PHP': 'php',
    'PowerShell': 'powershell', # spec: 'Powershell'
    'Pug': 'jade',
    'Python': 'python',
    'R': 'r',
    'Razor': 'razor', # spec: 'Razor (cshtml)'
    'Ruby': 'ruby',
    'Rust': 'rust',
    #'SCSS': 'scss (syntax using curly brackets), sass (indented syntax)', #TODO
    'Scala': 'scala',
    #'ShaderLab': 'shaderlab', # not in CudaText
    'Bash script': 'shellscript', # spec: 'Shell Script (Bash)'
    'SQL': 'sql',
    'Swift': 'swift',
    'TypeScript': 'typescript',
    #'TypeScript React': 'typescriptreact', # Not in CudaText
    #'TeX': 'tex', # Not in CudaText
    #'Visual Basic': 'vb', # Not in CudaText
    'XML': 'xml',
    'XSLT': 'xsl', # spec: 'XSL'
    'YAML': 'yaml',
}
