# Shortcuts

Handy keys for the Code Editor and for Claude Code. `Cmd` is for Mac. Everyone else uses `Ctrl`.

## Code Editor (VS Code)

!!! note "Browser editor"
    The workshop Code Editor runs in your browser. The browser can grab a few keys before the editor sees them (`Ctrl+W`, `Ctrl+T`, `Ctrl+N`).
    If a shortcut does nothing, open the command palette with `F1` and search for the action by name.

### Terminal

| Action | Windows / Linux | Mac |
|---|---|---|
| Show or hide the terminal | ``Ctrl+` `` | ``Ctrl+` `` |
| Show or hide the whole bottom panel | `Ctrl+J` | `Cmd+J` |
| Open a new terminal | ``Ctrl+Shift+` `` | ``Ctrl+Shift+` `` |
| Switch to the next or previous terminal | `Ctrl+PageDown` / `Ctrl+PageUp` | `Cmd+Shift+]` / `Cmd+Shift+[` |
| Split the terminal | `Ctrl+Shift+5` | `Cmd+\` |
| Copy and paste in the terminal | `Ctrl+Shift+C` / `Ctrl+Shift+V` | `Cmd+C` / `Cmd+V` |
| Close the current terminal | type `exit`, or click the bin icon | type `exit`, or click the bin icon |

!!! tip "Every new terminal needs the credentials again"
    Each new terminal starts without your `WSParticipantRole` credentials. See [Open your environment](../getting-started/environment.md).

### Around the editor

| Action | Windows / Linux | Mac |
|---|---|---|
| Command palette (run anything by name) | `Ctrl+Shift+P` or `F1` | `Cmd+Shift+P` or `F1` |
| Open a file by name | `Ctrl+P` | `Cmd+P` |
| Show or hide the side bar | `Ctrl+B` | `Cmd+B` |
| Search across all files | `Ctrl+Shift+F` | `Cmd+Shift+F` |
| Search in the current file | `Ctrl+F` | `Cmd+F` |
| Split the editor side by side | `Ctrl+\` | `Cmd+\` |
| Focus the editor from the terminal | `Ctrl+1` | `Cmd+1` |
| Preview a markdown file | `Ctrl+Shift+V` | `Cmd+Shift+V` |
| Zen mode (hide everything but the editor) | `Ctrl+K` then `Z` | `Cmd+K` then `Z` |

## Claude Code

### Keys

| Action | Key |
|---|---|
| Stop what Claude is doing | `Esc` |
| Go back to an earlier message and edit it | `Esc` twice |
| Switch between normal, accept-edits and plan mode | `Shift+Tab` |
| Cancel the current input. Press twice to quit | `Ctrl+C` |
| Quit | `Ctrl+D` |
| Clear the screen | `Ctrl+L` |
| Bring back an earlier prompt | `Up` arrow |
| New line in your prompt without sending | `Shift+Enter`, or `\` then `Enter` |

### In the prompt

| Type | What it does |
|---|---|
| `/` | Lists the slash commands |
| `@` | Picks a file or folder to point Claude at, for example `@squads/kyc/charter.md` |
| `!` then a command | Runs that shell command from inside Claude Code, for example `! make verify-capstone SQUAD=kyc CHECK=C1` |

### Slash commands you will use

| Command | What it does |
|---|---|
| `/status` | Shows the active model and where the setting came from |
| `/model` | Switches the model for this session. Only the models in [Open your environment](../getting-started/environment.md) work |
| `/clear` | Starts a fresh conversation, so old context stops affecting answers |
| `/compact` | Summarises a long conversation to free up space |
| `/resume` | Reopens an earlier conversation |
| `/help` | Lists everything your version supports |

### Start-up options

| Command | What it does |
|---|---|
| `claude` | Starts a new session in the current folder |
| `claude --continue` | Picks up the most recent session |
| `claude --resume` | Lets you choose an earlier session |

Run Claude Code from the repo root (`~/dezerv`), so it picks up `CLAUDE.md`. Shortcuts can change between versions, so `/help` is the final word.
