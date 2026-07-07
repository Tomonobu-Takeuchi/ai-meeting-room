# AI-PERSONA会議室 DB日次バックアップ（運用設計書v27 6章準拠）
# 仕様：pg_dump → AES-256 ZIP → 日次7日保持＋月次12ヶ月保持 → Google Driveへ第2系統コピー
$ErrorActionPreference = "Stop"

$BackupRoot = "C:\Claude\AI_Project\backups"
$DailyDir   = Join-Path $BackupRoot "daily"
$MonthlyDir = Join-Path $BackupRoot "monthly"
$LogFile    = Join-Path $BackupRoot "backup_log.txt"
$EnvFile    = Join-Path $BackupRoot "backup.env"
$PgDump     = "C:\Program Files\PostgreSQL\18\bin\pg_dump.exe"
$SevenZip   = "C:\Program Files\7-Zip\7z.exe"
$DriveDir   = "G:\マイドライブ\AI_Paradise_Backups"

function Write-Log($level, $msg) {
    $line = "{0} [{1}] {2}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $level, $msg
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
    Write-Host $line
}

try {
    New-Item -ItemType Directory -Force -Path $DailyDir, $MonthlyDir | Out-Null

    # --- 設定読込（backup.env） ---
    if (-not (Test-Path $EnvFile)) { Write-Log "ERROR" "backup.env not found"; exit 1 }
    $cfg = @{}
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match "^\s*([^#=]+)=(.*)$") { $cfg[$Matches[1].Trim()] = $Matches[2].Trim() }
    }
    if (-not $cfg["DATABASE_PUBLIC_URL"] -or -not $cfg["ZIP_PASSWORD"]) {
        Write-Log "ERROR" "backup.env missing DATABASE_PUBLIC_URL or ZIP_PASSWORD"; exit 1
    }

    # --- pg_dump ---
    $stamp   = Get-Date -Format "yyyyMMdd_HHmmss"
    $sqlFile = Join-Path $DailyDir "backup_$stamp.sql"
    & $PgDump $cfg["DATABASE_PUBLIC_URL"] -F p -f $sqlFile
    if ($LASTEXITCODE -ne 0) { Write-Log "ERROR" "pg_dump failed (exit $LASTEXITCODE)"; exit 1 }
    $sqlSize = (Get-Item $sqlFile).Length
    if ($sqlSize -lt 10KB) { Write-Log "ERROR" "dump too small ($sqlSize bytes) - aborting"; exit 1 }

    # --- AES-256 ZIP化 → 平文削除 ---
    $zipFile = Join-Path $DailyDir "backup_$stamp.zip"
    & $SevenZip a -tzip "-mem=AES256" ("-p" + $cfg["ZIP_PASSWORD"]) $zipFile $sqlFile | Out-Null
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $zipFile)) {
        Write-Log "ERROR" "7-Zip failed (exit $LASTEXITCODE)"; exit 1
    }
    Remove-Item $sqlFile -Force
    $zipSize = [math]::Round((Get-Item $zipFile).Length / 1MB, 2)

    # --- 月次保持：当月分がまだ無ければコピー ---
    $ym = Get-Date -Format "yyyyMM"
    if (-not (Get-ChildItem $MonthlyDir -Filter "backup_$ym*.zip" -ErrorAction SilentlyContinue)) {
        Copy-Item $zipFile $MonthlyDir
        Write-Log "INFO" "monthly copy created for $ym"
    }

    # --- ローテーション：日次7日・月次366日 ---
    Get-ChildItem $DailyDir -Filter "backup_*.zip" |
        Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-7) } |
        ForEach-Object { Remove-Item $_.FullName -Force; Write-Log "INFO" "rotated daily: $($_.Name)" }
    Get-ChildItem $MonthlyDir -Filter "backup_*.zip" |
        Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-366) } |
        ForEach-Object { Remove-Item $_.FullName -Force; Write-Log "INFO" "rotated monthly: $($_.Name)" }

    # --- 第2系統：Google Driveへコピー（失敗しても本体は成功扱い） ---
    try {
        New-Item -ItemType Directory -Force -Path $DriveDir | Out-Null
        Copy-Item $zipFile $DriveDir -Force
        # Drive側も直近7日分のみ保持
        Get-ChildItem $DriveDir -Filter "backup_*.zip" |
            Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-7) } |
            ForEach-Object { Remove-Item $_.FullName -Force }
        Write-Log "INFO" "copied to Google Drive"
    } catch {
        Write-Log "WARNING" "Google Drive copy failed: $($_.Exception.Message)"
    }

    Write-Log "SUCCESS" "backup_$stamp.zip created (${zipSize}MB, sql ${sqlSize}bytes)"

    # --- デッドマンスイッチ：healthchecks.ioへ成功ping（未設定なら何もしない） ---
    if ($cfg["HEALTHCHECK_URL"]) {
        try {
            Invoke-RestMethod -Uri $cfg["HEALTHCHECK_URL"] -TimeoutSec 10 | Out-Null
            Write-Log "INFO" "healthcheck ping sent"
        } catch {
            Write-Log "WARNING" "healthcheck ping failed: $($_.Exception.Message)"
        }
    }
    exit 0
} catch {
    Write-Log "ERROR" $_.Exception.Message
    exit 1
}
