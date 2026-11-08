# -*- coding: utf-8 -*-
<#
.SYNOPSIS
    ana-award-search GitHub 自動同期スクリプト
.DESCRIPTION
    1. リモート (origin) と専用ブランチ (auto-sync) の存在を確認
    2. git pull --rebase origin auto-sync を実行
    3. 変更がある場合、auto-sync ブランチへ git push（main への直接 push は一切禁止）
    4. 実行ログを logs/auto_sync.log に日時付きで記録
#>

param(
    [string]$BranchName = "auto-sync",
    [string]$RemoteName = "origin"
)

if (-not (Get-Command "git" -ErrorAction SilentlyContinue)) {
    $env:Path = "C:\Program Files\Git\cmd;" + [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
}

$ErrorActionPreference = "Continue"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$LogDir = Join-Path $RepoRoot "logs"
$LogFile = Join-Path $LogDir "auto_sync.log"

if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}

function Write-SyncLog {
    param([string]$Message, [string]$Level = "INFO")
    $Timestamp = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    $Line = "[$Timestamp] [$Level] $Message"
    Add-Content -Path $LogFile -Value $Line -Encoding UTF8
    Write-Output $Line
}

Push-Location $RepoRoot
try {
    Write-SyncLog "=== auto_sync 開始 (RepoRoot: $RepoRoot, TargetBranch: $BranchName) ==="

    if (-not (Test-Path (Join-Path $RepoRoot ".git"))) {
        Write-SyncLog "Git リポジトリ (.git) が初期化されていません。処理を停止します。" "ERROR"
        exit 1
    }

    $Remotes = (git remote) -split "`r?`n"
    if (-not ($Remotes -contains $RemoteName)) {
        Write-SyncLog "リモート '$RemoteName' が設定されていません。停止します。" "ERROR"
        exit 2
    }

    $RemoteUrl = (git remote get-url $RemoteName).Trim()
    if ([string]::IsNullOrWhiteSpace($RemoteUrl)) {
        Write-SyncLog "リモート '$RemoteName' の URL が空です。処理を停止します。" "ERROR"
        exit 2
    }

    if ($BranchName -eq "main" -or $BranchName -eq "master") {
        Write-SyncLog "安全規約違反: main/master ブランチへの直接自動 push は禁止されています (指定: $BranchName)。" "ERROR"
        exit 3
    }

    $CurrentBranch = (git rev-parse --abbrev-ref HEAD).Trim()
    if ($CurrentBranch -ne $BranchName) {
        $LocalBranches = (git branch --list $BranchName)
        if ($LocalBranches) {
            git checkout $BranchName 2>&1 | Out-Null
        } else {
            git checkout -b $BranchName 2>&1 | Out-Null
        }
        Write-SyncLog "ブランチを '$BranchName' に切り替えました。"
    }

    $RemoteBranchExists = git ls-remote --heads $RemoteName $BranchName
    if ($RemoteBranchExists) {
        Write-SyncLog "git pull --rebase $RemoteName $BranchName を実行中..."
        $HasLocalChanges = (git status --porcelain)
        if ($HasLocalChanges) {
            git stash push -u -m "auto-sync-temp" 2>&1 | Out-Null
        }
        $PullOutput = git pull --rebase $RemoteName $BranchName 2>&1
        $PullStatus = $LASTEXITCODE
        if ($HasLocalChanges) {
            git stash pop 2>&1 | Out-Null
        }
        if ($PullStatus -ne 0) {
            Write-SyncLog "git pull --rebase 中にエラーが発生しました: $PullOutput" "ERROR"
            git rebase --abort 2>&1 | Out-Null
            exit 4
        }
    }

    $StatusLines = git status --porcelain
    if ($StatusLines) {
        $NowTag = (Get-Date).ToString("yyyy-MM-dd HH:mm")
        git add -A 2>&1 | Out-Null
        $StagedCode = @(git diff --cached --name-only)
        if ($StagedCode.Count -gt 0) {
            $FileCount = $StagedCode.Count
            $SampleFiles = ($StagedCode | Select-Object -First 3) -join ", "
            $CodeMsg = "auto: $NowTag $($FileCount)ファイル変更 ($SampleFiles)"
            git commit -m $CodeMsg 2>&1 | Out-Null
            Write-SyncLog "コミット完了: $CodeMsg"
        }
    }

    $Unpushed = git log "$RemoteName/$BranchName..HEAD" --oneline 2>&1
    if ($Unpushed) {
        Write-SyncLog "git push -u $RemoteName $BranchName を実行中..."
        $PushOutput = git push -u $RemoteName $BranchName 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-SyncLog "git push に失敗しました: $PushOutput" "ERROR"
            exit 5
        }
        $HeadHash = (git rev-parse HEAD).Trim()
        Write-SyncLog "=== auto_sync 正常完了 (Branch: $BranchName, PushCommit: $HeadHash) ==="
    } else {
        Write-SyncLog "リモートと同期済みです（未プッシュコミットなし）。"
    }

    exit 0
}
catch {
    Write-SyncLog "未処理例外が発生しました: $($_.Exception.Message)" "ERROR"
    exit 99
}
finally {
    Pop-Location
}
