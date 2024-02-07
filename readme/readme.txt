Plugin for CudaText.

#### About Codeium

  A Free AI-Powered Toolkit for Developers. https://codeium.com/

#### About addon

  AI Autocomplete and AI Chat using Codeium (free Copilot alternative)

#### Installation

  1. Run command Codeium: Get new token... Web page will be opened.
  2. Log in (or register) and skip to the page with a token.
  3. Copy token to clipboard, paste it to CudaText dialog which asks for it.
  Now you should be logged in. Server executable will be downloaded and started automatically.

To automatically start Codeium use "Toggle: log in on startup" command.
"TAB completion" mode can be enabled with `tab_completion` option in config, use `Codeium: Config` command.
Also you can set hotkey for `Get completions` command. For example Alt+\. This will give a list of completions.
For chatting with AI, use command `Codeium: Chat...`


Enjoy!

#### Configuration

`tab_completion` - completion by using TAB key. completion hint will be shown in the top-right corner.

`append_mode` - new chat questions/answers will be appended to old ones. disable it to clear chat on every question.

`version` - locked version of language server. you can update by setting this option to a new value and deleting old server binary.

#### FAQ

 - How to stop request?
 - User can stop request by pressing ESC/Space/Enter
 
 - How to make tab completion hint appear faster?
 - Tune the following CudaText settings:
   "py_change_slow"
   "ui_timer_idle"


Author: veksha (https://github.com/veksha)
License: MIT