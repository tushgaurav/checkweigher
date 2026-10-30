<#
Portable PostgreSQL 17 (+ TimescaleDB if installed) for local development on Windows.
No installer or admin rights needed; everything lives in .devtools\ (git-ignored).

  .\scripts\dev-db.ps1 init     # download (if needed), initdb, create role/db
  .\scripts\dev-db.ps1 start
  .\scripts\dev-db.ps1 stop
  .\scripts\dev-db.ps1 status
  .\scripts\dev-db.ps1 psql     # interactive shell on the dev database
  .\scripts\dev-db.ps1 reset    # drop and recreate the dev database (destructive)
#>
param([Parameter(Mandatory = $true)][ValidateSet("init", "start", "stop", "status", "psql", "reset")] [string]$Command)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Tools = Join-Path $Root ".devtools"
$PgHome = Join-Path $Tools "pgsql"
$PgBin = Join-Path $PgHome "bin"
$Data = Join-Path $Tools "pgdata"
$Log = Join-Path $Tools "postgres.log"
$Port = 5433
$PgZipUrl = "https://sbp.enterprisedb.com/getfile.jsp?fileid=1260616"   # PostgreSQL 17.11 Windows x64 binaries
$TsVersion = "2.31.0"
$TsZipUrl = "https://github.com/timescale/timescaledb/releases/download/$TsVersion/timescaledb-postgresql-17-windows-amd64.zip"
$TsZipSha256 = "1A79207D46ECDF626D4FD39310DA3A490CFEC13CBB5E9510413B748F512AE2F4"   # from the GitHub release asset digest

function Install-Postgres {
    New-Item -ItemType Directory -Force -Path $Tools | Out-Null
    if (-not (Test-Path (Join-Path $PgBin "postgres.exe"))) {
        $zip = Join-Path $Tools "pg17.zip"
        if (-not (Test-Path $zip)) { curl.exe -L --fail -o $zip $PgZipUrl }
        tar -xf $zip -C $Tools
    }
}

function Install-Timescale {
    if (Test-Path (Join-Path $PgHome "lib\timescaledb.dll")) { return }
    $zip = Join-Path $Tools "timescaledb-pg17.zip"
    if (-not (Test-Path $zip) -or (Get-Item $zip).Length -eq 0) { curl.exe -L --fail -o $zip $TsZipUrl }
    if ((Get-FileHash $zip -Algorithm SHA256).Hash -ne $TsZipSha256) { throw "checksum mismatch for $zip (incomplete download?)" }
    $dest = Join-Path $Tools "timescaledb-pg17"
    New-Item -ItemType Directory -Force -Path $dest | Out-Null
    tar -xf $zip -C $dest
    $src = Get-ChildItem -Path $dest -Recurse -Filter "timescaledb.control" | Select-Object -First 1
    $pkg = $src.Directory.FullName
    Copy-Item (Join-Path $pkg "*.dll") (Join-Path $PgHome "lib") -Force
    Copy-Item (Join-Path $pkg "timescaledb.control") (Join-Path $PgHome "share\extension") -Force
    Copy-Item (Join-Path $pkg "timescaledb--*.sql") (Join-Path $PgHome "share\extension") -Force
}

function Invoke-Psql([string]$Db, [string]$Sql) {
    & (Join-Path $PgBin "psql.exe") -h localhost -p $Port -U postgres -d $Db -v ON_ERROR_STOP=1 -c $Sql
    if ($LASTEXITCODE -ne 0) { throw "psql failed: $Sql" }
}

function Start-Db {
    & (Join-Path $PgBin "pg_ctl.exe") -D $Data status *> $null
    if ($LASTEXITCODE -eq 0) { Write-Host "already running"; return }
    # Start-Process so the server does not inherit (and hold open) this shell's stdout pipe.
    # WaitForExit() rather than -Wait: -Wait also waits for the server child process.
    $p = Start-Process -FilePath (Join-Path $PgBin "pg_ctl.exe") -WindowStyle Hidden -PassThru `
        -ArgumentList @("-D", "`"$Data`"", "-l", "`"$Log`"", "-o", "`"-p $Port`"", "-w", "start")
    $p.WaitForExit()
    if ($p.ExitCode -ne 0) { throw "pg_ctl start failed; see $Log" }
}

switch ($Command) {
    "init" {
        Install-Postgres
        try { Install-Timescale } catch { Write-Warning "TimescaleDB not installed ($_); plain PostgreSQL views will be used" }
        $confFile = Join-Path $Data "postgresql.conf"
        if (-not (Test-Path (Join-Path $Data "PG_VERSION"))) {
            & (Join-Path $PgBin "initdb.exe") -D $Data -U postgres --auth=trust -E UTF8 --locale=C
            Add-Content -Path $confFile -Value @("listen_addresses = 'localhost'", "port = $Port", "timezone = 'UTC'")
        }
        if ((Test-Path (Join-Path $PgHome "lib\timescaledb.dll")) -and -not (Select-String -Path $confFile -Pattern "^shared_preload_libraries" -Quiet)) {
            Add-Content -Path $confFile -Value @("shared_preload_libraries = 'timescaledb'", "timescaledb.telemetry_level = off")
            & (Join-Path $PgBin "pg_ctl.exe") -D $Data status *> $null
            if ($LASTEXITCODE -eq 0) { & (Join-Path $PgBin "pg_ctl.exe") -D $Data -m fast stop }
        }
        Start-Db
        Invoke-Psql "postgres" "DO `$`$BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'cw') THEN CREATE ROLE cw LOGIN SUPERUSER PASSWORD 'cw'; END IF; END`$`$;"
        $exists = & (Join-Path $PgBin "psql.exe") -h localhost -p $Port -U postgres -tAc "SELECT 1 FROM pg_database WHERE datname = 'checkweigher'"
        if (-not $exists) { Invoke-Psql "postgres" "CREATE DATABASE checkweigher OWNER cw" }
        Write-Host "Dev database ready: postgresql://cw:cw@localhost:$Port/checkweigher"
    }
    "start" { Start-Db }
    "stop" { & (Join-Path $PgBin "pg_ctl.exe") -D $Data -m fast stop }
    "status" { & (Join-Path $PgBin "pg_ctl.exe") -D $Data status }
    "psql" { & (Join-Path $PgBin "psql.exe") -h localhost -p $Port -U cw -d checkweigher }
    "reset" {
        Invoke-Psql "postgres" "DROP DATABASE IF EXISTS checkweigher WITH (FORCE)"
        Invoke-Psql "postgres" "CREATE DATABASE checkweigher OWNER cw"
    }
}
