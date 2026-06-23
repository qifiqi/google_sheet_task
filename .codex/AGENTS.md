# Codex Project Rules

## Windows PowerShell UTF-8

For this repository, treat text files as UTF-8 by default.

- Before printing Chinese text to the terminal in PowerShell, set:

```powershell
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
```

- When reading repository text files, always use explicit UTF-8:

```powershell
Get-Content <path> -Encoding UTF8
```

- Recommended patterns:

```powershell
Get-Content .\run.py -Encoding UTF8 -TotalCount 50
Get-Content .\README.md -Encoding UTF8
Get-Content .\run.py -Encoding UTF8 | Select-String "应用|乱码|编码"
```

- Prefer `rg` for text search when possible.
- Do not use bare `Get-Content` on repository text files unless the file encoding is known to be different.
