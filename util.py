from cudatext import *

def is_editor_valid(editor: Editor):
    return editor.get_prop(PROP_INDEX_TAB) != -1

def split_text_by_length(text, max_length, padding=False):
    lines_out = []
    for line in text.split('\n'):
        words = line.split()
        parts = []
        current_part = ''
        for word in words:
            if len(current_part) + len(word) <= max_length:
                if current_part:
                    current_part += ' ' + word
                else:
                    current_part = word
            else:
                parts.append(current_part)
                current_part = word
        if current_part:
            parts.append(current_part)
        
        if padding:
            s = line.strip()
            if s:
                spaces = line.index(s[0])
                parts = [' ' * spaces + part for part in parts]

        lines_out.extend(parts)
    
    if padding:
        max_length = max(len(line) for line in lines_out)
        lines_out = [line.ljust(max_length) for line in lines_out]

    return '\n'.join(lines_out)
    
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

