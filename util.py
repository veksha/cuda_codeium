from cudatext import *

def is_editor_valid(editor: Editor):
    return editor.get_prop(PROP_INDEX_TAB) != -1

def split_text_by_length(text, max_length, padding=False):
    last_space = 0
    last_newline = 0
    cur_line = 0
    out = ''
    lines = text.split('\n')
    
    i = 0
    for c in text:
        if c in (' ', '\t'):
            last_space = i
            out += c
            i += 1
            continue
        elif c == '\n':
            cur_line += 1
            last_newline = i
            out += c
            i += 1
            continue
            
        if i - last_newline <= max_length:
            out += c
            i += 1
        else:
            line = lines[cur_line]
            indent = len(line) - len(line.lstrip())
            indent_s = line[:indent]
            
            split_on_prev_space = i - last_space < i - last_newline
            if split_on_prev_space and i - last_newline > indent:
                out = out[:last_space] + '\n' + indent_s + out[last_space:] + c
                i += indent + 2
                last_newline = last_space
            else:
                out += c + '\n' + indent_s
                i += indent + 2
                last_newline = i
        
    if padding:
        lines_out = out.split('\n')
        max_length = max(len(line) for line in lines_out)
        lines_out = [line.ljust(max_length) for line in lines_out]
        return lines_out
    return out.split('\n')
    
    
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

