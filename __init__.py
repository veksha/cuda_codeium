import os, sys, json, gzip, io, tempfile, subprocess, requests, shutil, time, uuid
from concurrent.futures import ThreadPoolExecutor
from collections import namedtuple

from cudatext import *
import cudax_lib as apx
import cudatext_cmd as cmds

from .dlg import Dialog
from .util import split_text_by_length,language_enum,lex_ids,is_editor_valid

PLUGIN_NAME = __name__
LOG = False

IS_WIN = os.name=='nt'

API_URL = 'https://server.codeium.com'
HEADERS_JSON       = { 'Content-Type': 'application/json' }
HEADERS_GRPC_PROTO = { 'Content-Type': 'application/grpc+proto' }
SNIP_ID = PLUGIN_NAME+'__snip'

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

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

def bool_to_str(v): return '1' if v else '0'
def str_to_bool(s): return s=='1'
fn_config = os.path.join(app_path(APP_DIR_SETTINGS), PLUGIN_NAME+'.ini')
option_token = ''
option_api_key = ''
option_append_mode = True
option_version = '1.6.22'
option_tab_completion = False

Item = namedtuple('Item', 'hint text suffix text_inline text_inline_mask text_block start_position end_position cursor_offset')

SESSION_ID = str(uuid.uuid4())

class CancelException(Exception): pass
    
class Command:
    
    def __init__(self):
        self.name = 'codeium'
        self.port = None
        self.token = None
        self.api_key = None
        self.manager_dir = None
        self.text = '# print hello world in nim language\n'
        self.row = 1
        self.col = 0
        self.process = None
        self.caret_view = None
        
        global option_token
        global option_api_key
        global option_append_mode
        global option_version
        global option_tab_completion
        option_token = ini_read(fn_config, 'op', 'token', option_token)
        option_api_key = ini_read(fn_config, 'op', 'api_key', option_api_key)
        option_append_mode = str_to_bool(ini_read(fn_config, 'op', 'append_mode', bool_to_str(option_append_mode)))
        option_tab_completion = str_to_bool(ini_read(fn_config, 'op', 'tab_completion', bool_to_str(option_tab_completion)))
        option_version = ini_read(fn_config, 'op', 'version', option_version)
        self.token = option_token
        self.api_key = option_api_key
        
        self.conversations = {}
        self.in_process_of_creating_new_tab = False
        self.in_process_of_answering = False
        self.in_process_of_asking = False
        self.cancel = False
        self.messages = []
        self.completions = []
        self.completion_allowed = False
        self.go_to_end = True
        self.comp_requests_active = 0
        self.comp_result_list = {}
        self.shutting_down = False
        self.ask_command_was_triggered = False
        
        
    def config(self):
        ini_write(fn_config, 'op', 'append_mode', bool_to_str(option_append_mode))
        ini_write(fn_config, 'op', 'tab_completion', bool_to_str(option_tab_completion))
        ini_write(fn_config, 'op', 'version', option_version)
        file_open(fn_config)
        
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
            response = requests.post(url, headers=HEADERS_JSON, data=data, timeout=4)
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
            option_version,
            BIN_SUFFIX
        )
        
        msg_status('{}: Downloading server...'.format(self.name), process_messages=True)
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
    
    def get_server_info(self):
        import datetime
        msg_status("Gathering Codeium server info..", True)
        info = ''
        local_timestamp = None
        try:
            ex = self.get_executable()
            output = subprocess.check_output([ex, '--stamp']).decode()
            import re
            match = re.search(r'BUILD_TIMESTAMP: (\d+)', output)
            if match is not None:
                stamp = int(match.group(1))
                local_timestamp = datetime.datetime.fromtimestamp(stamp)
                info = "Executable: {}\nTimestamp: {}\nPort: {}\n\n".format(
                    ex, local_timestamp, self.port
                )
        except:
            info += "Can't get Codeium server binary info\n\n"
            
        info += "Version in config:\t{}\n".format(option_version)
        
        try:
            url = "https://api.github.com/repos/Exafunction/codeium/releases/latest"
            response = requests.get(url)
            data = response.json()
            new_timestamp = datetime.datetime.strptime(data['published_at'], '%Y-%m-%dT%H:%M:%SZ')
            normal_format = new_timestamp.strftime('%Y-%m-%d %H:%M:%S')
            name = data['name'].lstrip("language-server-v")
            new_version = "New version:\t\t{}\nTimestamp: {}".format(name, normal_format)
            info += new_version
            if local_timestamp is not None:
                if local_timestamp < new_timestamp:
                    info += "\n\nTo update your server binary, delete old one and change version in config."
                
        except:
            info += "Can't get Codeium update info."
        msg_box(info, MB_ICONINFO)
    
    def toggle_log_in_on_startup(self):
        event = 'on_start2'
        s = ini_read('plugins.ini', 'events', __name__, '')
        s = '' if s == event else event
        ini_write('plugins.ini', 'events', __name__, s)
        
        if s:
            print('{}: Log in on startup enabled'.format(self.name))
        else:
            print('{}: Log in on startup disabled'.format(self.name))
        
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
        
        def sub(*args, **kwargs):
            self.run_server(self.executable, self.manager_dir)
        timer_proc(TIMER_START_ONE, sub, 50)
        
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
            self.shutting_down = False
            n = 0
            while self.port is None:
                self.find_port()
                if self.port:
                    break
                time.sleep(0.3)
                n += 1
                # 0.3*25 - waiting ~7.5 seconds for port file
                if n > 25 or self.shutting_down:
                    #print("ERROR: {}: {}".format(
                    #    self.name, "port can't be found. please, try again.")
                    #)
                    self.shutdown()
                    self.shutting_down = False
                    break
                
        with ThreadPoolExecutor() as ex:
            future = ex.submit(wait_for_port_file)
            
            while not future.done():
                app_idle()
                time.sleep(0.001)
            
            if self.port:
                timer_proc(TIMER_STOP,  self.heartbeat, 5000)
                timer_proc(TIMER_START, self.heartbeat, 5000)
                msg_status("{}: Logged in".format(self.name))
                
                if self.ask_command_was_triggered:
                    self.ask_command_was_triggered = False
                    timer_proc(TIMER_START_ONE, lambda _: self._ask(), 50)
        
    def find_port(self, tag=''):
        import re
        files = os.listdir(self.manager_dir)
        num_files = [f for f in files if re.match(r'^\d+$', f)]
        if num_files:
            self.port = int(num_files[0])
            pass;    LOG and print("Found port:", self.port)
            
            
    def get_completions(self, use_hint=False):
        self.hide_hint()
        if self.port is None:
            self.log_in()
            if self.port is None:
                return
            
        with ThreadPoolExecutor() as ex:
            self.comp_requests_active += 1
            future = ex.submit(self.request_completions)
            while not future.done():
                app_idle()
                time.sleep(0.001)
            self.comp_requests_active -= 1
            items = future.result()
            self.comp_result_list[self.comp_requests_active] = items
            
        # we interested only in newest result
        if self.comp_requests_active != 0:
            return
        
        # newest is with max key (!)
        max_key = max(self.comp_result_list.keys())
        items = self.comp_result_list[max_key]

        if items is None:
            return
        
        self.comp_result_list.clear()
        
        result = 'result' if len(items) == 1 else 'results'
        msg_status("{}: Got {} {}".format(self.name, len(items), result))
        
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
            
            def rep_chars(text):
                return text.replace('\n',' ').replace('\t',' ')
            
            if text_inline:
                hint = rep_chars(text_inline) + ' ' + rep_chars(text_block)
            else:
                hint = rep_chars(text)
            
            completions.append(Item(
                hint.strip(),
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
        
        if use_hint:
            if completions:
                #hint = completions[0].hint
                hint = completions[0].text + completions[0].suffix
                self.show_hint(hint)
            else:
                self.hide_hint()
        else:
            ed.complete_alt('\n'.join(words), SNIP_ID, len_chars=0)

    def show_hint(self, hint):
        ed.set_prop(PROP_CORNER2_COLOR_FONT, 0x676767)
        ed.set_prop(PROP_CORNER2_COLOR_BACK, 0xf4f4f4)
        ed.set_prop(PROP_CORNER2_TEXT, split_text_by_length(hint.strip(), 50, padding=True))
        self.completion_allowed = True
    
    def hide_hint(self):
        ed.set_prop(PROP_CORNER2_TEXT, '')
        self.completion_allowed = False

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
                    'extension_version': option_version,
                    }
            }
            
            try:
                response = requests.post(url, headers=HEADERS_JSON, data=json.dumps(data), timeout=4)
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
    
    def on_click(self, ed_self, state):
        if self.go_to_end:
            ed_self.set_prop(PROP_SCROLL_VERT_SMOOTH, ed_self.get_prop(PROP_SCROLL_VERT_SMOOTH)-1)
            ed_self.cmd(cmds.cmd_MouseClickAtCursor)
        self.go_to_end = False
    
    def goto_end(self, editor: Editor):
        info = editor.get_prop(PROP_SCROLL_VERT_INFO)
        smooth_pos = info['smooth_pos']
        smooth_pos_last = info['smooth_pos_last']
        scroll_at_end = (abs(smooth_pos_last - smooth_pos) < 2)
        
        if self.go_to_end and scroll_at_end:
            editor.cmd(cmds.cCommand_GotoTextEnd) # moves caret
        
        # if caret on last line
        last_line = editor.get_line_count()-1
        y = editor.get_carets()[0][1]
        if y == last_line:
            self.go_to_end = True
        # if not, but scrolled to end with mouse wheel
        elif smooth_pos != 0 and scroll_at_end:
            self.go_to_end = True
    
    def set_text(self, editor: Editor, question, text):
        editor.set_text_all('### User:\n{}\n\n### Bot:\n{}'.format(question, text))
        self.goto_end(editor)
    
    def append_text(self, editor: Editor, text):
        last_line = editor.get_line_count()-1
        last_line_len = editor.get_line_len(last_line)
        
        editor.insert(last_line_len, last_line, text)
        self.goto_end(editor)
    
    def Ask(self):
        self.ask_command_was_triggered = True
        self._ask()
        
    def _ask(self):
        if self.in_process_of_asking:
            return
        
        self.in_process_of_asking = True
        try:
            if self.port is None:
                self.log_in()
            if self.port is not None:
                if self.in_process_of_creating_new_tab:
                    timer_proc(TIMER_START_ONE, lambda _: self._ask(), 100)
                else:
                    def callback(question):
                        if question:
                            self.request_GetChatMessage(question)
                    Dialog.input(callback)
        finally:
            self.in_process_of_asking = False
    
    def request_GetChatMessage(self, question):
        if self.in_process_of_answering:
            self.cancel = True
            timer_proc(TIMER_START_ONE, lambda _: self.request_GetChatMessage(question), 10)
            return
        
        url = 'http://127.0.0.1:{}/exa.language_server_pb.LanguageServerService/GetChatMessage'.format(
            self.port
        )
        
        from . import proto_pb2
        
        GetChatMessage_data = proto_pb2.GetChatMessageRequest()
        GetChatMessage_data.prompt = question or ''
        
        metadata = proto_pb2.Metadata()
        metadata.api_key = self.api_key
        metadata.ide_name = "vscode"
        metadata.locale = "en"
        metadata.ide_version = "Visual Studio Code 1.77.3"
        metadata.extension_version = option_version
        metadata.extension_name = "vscode"
        metadata.session_id = SESSION_ID
        #metadata.session_id = "50d517c6-ac4a-4d44-ab20-1d48e12ee70d"
        GetChatMessage_data.metadata.CopyFrom(metadata)
        
        from .google.protobuf.timestamp_pb2 import Timestamp
        import datetime
        now = datetime.datetime.now()
        timestamp = Timestamp()
        timestamp.FromDatetime(now)
        
        chat_message = proto_pb2.ChatMessage()
        chat_message.messageId = 'user-1'
        chat_message.intent.generic.text = GetChatMessage_data.prompt
        chat_message.source = 1
        chat_message.timestamp.CopyFrom(timestamp)
        
        unique_string = str(uuid.uuid4())
        #chat_message.conversationId = unique_string
        chat_message.conversationId = '8HTVPeFtS35MLqygNelEYA8Ky8Qd32jG'
        self.messages.append(chat_message)
        GetChatMessage_data.chat_messages.extend(self.messages)
        
        data = GetChatMessage_data.SerializeToString()
        compression_flag = b'\x00'
        data = compression_flag + len(data).to_bytes(4, 'big') + data
        
        msg_status('{}: waiting for bot..'.format(self.name), process_messages=True)
        
        self.in_process_of_asking = False
        self.in_process_of_answering = True
        messages = []
        try:
            response = requests.post(url, headers=HEADERS_GRPC_PROTO, data=data, timeout=8, stream=True)
            response.raise_for_status()
            error_count = 0
            prev_text_len = 0
            
            buffer = bytearray()
            for i, data in enumerate(response.iter_content(chunk_size=8192)):
                if self.cancel:
                    if messages: # partial answer must be saved to context as well
                        self.messages.append(messages[-1].chat_message)
                    raise CancelException
                
                buffer.extend(data)
                
                if len(buffer) >= 4:
                    message_size = int.from_bytes(buffer[1:5], byteorder='big')
                    if len(buffer) >= message_size + 5:
                        message_data = buffer[5:message_size + 5]
                        buffer = buffer[message_size + 5:]
                        
                        msg = None
                        try:
                            msg = proto_pb2.GetChatMessageResponse().FromString(message_data)
                        except Exception as e:
                            print("ERROR:", e)
                            error_count += 1
                            if error_count > 2:
                                print("ERROR: too many errors, aborting task.")
                                return
                            continue
                        
                        messages.append(msg)
                        editor = self.get_editor(msg.chat_message.conversationId, question)
                        if not is_editor_valid(editor):
                            raise CancelException
                        editor.set_prop(PROP_CARET_VIEW, '-100,-100')
                        if i == 0:
                            editor.focus()
                            self.update_tab_title(editor, question)
                        from .google.protobuf.internal import decoder
                        buf = messages[-1].chat_message.action.text
                        if buf:
                            # first byte is '\n' for some reason. some kind of mark?
                            buf = buf[1:] # skip it
                            # next we have varint? seems it's text size? what for? decode it and skip
                            varint, varint_len = decoder._DecodeVarint(buf, 0)
                            buf = buf[varint_len:]
                        text = buf.decode('utf-8', errors='replace')
                        if option_append_mode:
                            if i == 0:
                                if editor.get_line_count() > 1:
                                    self.append_text(editor, '\n\n')
                                self.go_to_end = True
                                editor.cmd(cmds.cCommand_GotoTextEnd)
                                self.append_text(editor, '### User:\n{}\n\n### Bot:\n'.format(question))
                            self.append_text(editor, text[prev_text_len:])
                            prev_text_len = len(text)
                        else:
                            self.set_text(editor, question, text)
                        app_idle()
            
            if not messages:
                msg_status('{}: no answer :('.format(self.name), process_messages=True)
            else:
                msg_status('{}: answer recieved'.format(self.name), process_messages=True)
                self.messages.append(messages[-1].chat_message)
            return
                    
        except requests.exceptions.Timeout:
            print("ERROR: GetChatMessage failed: The request timed out.")
            return
        except requests.exceptions.RequestException as e:
            print("ERROR: GetChatMessage failed. Error:", e)
            return
        except CancelException:
            #print("ERROR: User canceled request.")
            pass
        finally:
            self.cancel = False
            
            def sub(*args, **kwargs):
                self.in_process_of_answering = False
            timer_proc(TIMER_START_ONE, sub, 2000) # 2000 ~ py_caret_slow
            
            if messages and is_editor_valid(editor):
                editor.set_prop(PROP_CARET_VIEW, self.caret_view)
                editor.set_prop(PROP_MODIFIED, False)
                for line in range(editor.get_line_count()):
                    editor.set_prop(PROP_LINE_STATE, (line, LINESTATE_NORMAL))
            
    def update_tab_title(self, editor, title):
        title = title.replace('\n', ' ')[:50]
        editor.set_prop(PROP_TAB_TITLE, 'Bot | {}'.format(title))
    
    def get_editor(self, conversation_id, question):
        ed_handle = self.conversations.get(conversation_id, None)
        if not ed_handle:
            self.in_process_of_creating_new_tab = True
            file_open('')
            if ed.get_filename('*') == '' and ed.get_text_all() == '': # ensure we are at correct tab
                ed_handle = ed.get_prop(PROP_HANDLE_SELF)
                self.conversations[conversation_id] = ed_handle
                self.in_process_of_creating_new_tab = False
    
                self.update_tab_title(ed, question)
                ed.set_prop(PROP_LEXER_FILE, 'Markdown')
                ed.set_prop(PROP_WRAP, WRAP_ON_WINDOW)
                ed.set_prop(PROP_LAST_LINE_ON_TOP, False)
                self.caret_view = ed.get_prop(PROP_CARET_VIEW)
        return Editor(ed_handle)
    
    def request_completions(self, *args):
        if self.port is None:
            print("ERROR: Can't get completions: server is not started.")
            return
        
        url = 'http://127.0.0.1:{}/exa.language_server_pb.LanguageServerService/GetCompletions'.format(
            self.port
        )
        
        self.text = ed.get_text_all()
        self.col, self.row = ed.get_carets()[0][:2]
        line_len = ed.get_line_len(self.row)
        if line_len is None:
            return # fix TypeError: '>' not supported between instances of 'NoneType' and 'int'
        if line_len > 0 and self.col > line_len:
           self.col = line_len
        
        lexer = ed.get_prop(PROP_LEXER_FILE)
        lang =  language_enum.get(lex_ids.get(lexer,'plaintext'), 30)
        lexer = lexer or 'plaintext'
        
        data = {
            'metadata': {
                'api_key': self.api_key,
                'ide_name': 'vscode',
                'ide_version': '1.77.3',
                'extension_version': option_version,
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
            response = requests.post(url, headers=HEADERS_JSON, data=json.dumps(data), timeout=4)
            response.raise_for_status()
        except requests.exceptions.Timeout:
            # no need to print
            #print("ERROR: Can't get completions: The request timed out")
            return
        except requests.exceptions.RequestException as e:
            print("ERROR: Can't get completions. Error:", e)
            return
        result = response.content
        
        result_str = result.decode('utf-8')
        result_json = json.loads(result_str)
        
        items = result_json.get('completionItems', [])
        return items
        
    def shutdown(self, *args, **vargs):
        msg_status('{}: Shutting down'.format(self.name))
        
        self.shutting_down = True
        self.port = None
        timer_proc(TIMER_STOP,  self.heartbeat, 5000)
        
        if self.process:
            if IS_WIN:
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                subprocess.call(['taskkill', '/F', '/T', '/PID',  str(self.process.pid)], startupinfo=startupinfo)
            else:
                self.process.terminate()
                self.process.wait()
            self.process = None


    def on_close(self, ed_self: Editor):
        '''
        Remove conversation from dict when the tab is closed.
        '''
        ed_h = ed_self.get_prop(PROP_HANDLE_SELF)
        to_pop = [k for k, v in self.conversations.items() if v == ed_h]
        
        for conversation_id in to_pop:
            self.conversations.pop(conversation_id, None)
        
        if to_pop:
            self.cancel = True

    def on_exit(self, ed_self):
        self.shutdown()
        
    def on_key(self, ed_self, key, state):
        if self.in_process_of_answering and key in (13, 27, 32):
            ed_h = ed_self.get_prop(PROP_HANDLE_SELF)
            if ed_h in self.conversations.values():
                self.cancel = True
                msg_status('{}: User canceled request.'.format(self.name))
        elif key == 27:
            self.hide_hint()
        elif key == 9 and option_tab_completion:
            if self.completions and self.completion_allowed:
                item = self.completions[0]
                  
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
                
                self.hide_hint()
                return False 
    
    def on_change_slow(self, ed_self):
        if option_tab_completion and not self.in_process_of_answering:
            self.get_completions(use_hint=True)
            
    def on_caret(self, ed_self):
        self.hide_hint()
    
    def on_start2(self, ed_self):
        self.log_in()
        
