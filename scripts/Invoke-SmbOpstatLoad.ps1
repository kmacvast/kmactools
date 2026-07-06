<#
.SYNOPSIS
    Continuous SMB load generator for vast-opstat TUI validation.

.DESCRIPTION
    Runs until Ctrl+C. Exercises SMBCommon / ViewMetrics signals that
    vast-opstat --smb displays:

      Health / Insights     - total iops, latency, bandwidth, workload mix
      Data Path (READ)      - random + sequential reads (small/large blocks)
      Data Path (WRITE)     - sequential + random writes
      Metadata panel        - create/close/delete, directory walks, setattr
      Classifier labels     - metadata-heavy, read-biased, write-biased phases

    Default share targets var203 opstattest view for drill-down (`v`).

    Compatible with Windows PowerShell 5.1+. Optional diskspd accelerates
    data-path load when present at -DiskspdPath.

.PARAMETER NasShare
    UNC SMB share root (default: \\172.200.203.6\opstattest).

.PARAMETER DiskspdPath
    Path to diskspd.exe. When missing, .NET file I/O loops are used instead.

.PARAMETER PhaseSeconds
    Seconds per emphasis phase before rotating workload bias label.

.EXAMPLE
    .\Invoke-SmbOpstatLoad.ps1

.EXAMPLE
    .\Invoke-SmbOpstatLoad.ps1 -NasShare '\\172.200.203.6\opstattest' -PhaseSeconds 120
#>

[CmdletBinding()]
param(
    [string] $NasShare      = '\\172.200.203.6\opstattest',
    [string] $DiskspdPath   = 'C:\Diskspd\amd64\diskspd.exe',
    [int]    $PhaseSeconds = 90,
    [int]    $MetaWorkers   = 4,
    [int]    $DirWorkers    = 2
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# ── Paths ────────────────────────────────────────────────────────────────────
$TestRoot     = Join-Path $NasShare 'opstat_smb_load'
$DataDir      = Join-Path $TestRoot 'data'
$MetaDir      = Join-Path $TestRoot 'metadata'
$TraverseDir  = Join-Path $TestRoot 'traverse'
$LocalTemp    = Join-Path $env:TEMP 'smb_opstat_load'
$CompressSrc  = Join-Path $LocalTemp 'compressible.txt'
$RandomDat    = Join-Path $DataDir 'stress_random.dat'
$SeqDat       = Join-Path $DataDir 'stress_seq.dat'
$ReadDat      = Join-Path $DataDir 'stress_read.dat'
$LockFile     = Join-Path $DataDir 'lock_stress.dat'

$script:WorkerJobs    = @()
$script:PhaseIndex    = 0
$script:PhaseNames    = @(
    'balanced mixed I/O + metadata',
    'read-biased (large-block sequential reads)',
    'write-biased (sequential writes)',
    'metadata-heavy (create/list/delete churn)',
    'small-file metadata burst'
)

function Write-Status {
    param([string] $Message, [ConsoleColor] $Color = 'Gray')
    $ts = Get-Date -Format 'HH:mm:ss'
    Write-Host "[$ts] $Message" -ForegroundColor $Color
}

function Ensure-Directory {
    param([string] $Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
    }
}

function Initialize-TestLayout {
    Ensure-Directory $TestRoot
    Ensure-Directory $DataDir
    Ensure-Directory $MetaDir
    Ensure-Directory $TraverseDir
    Ensure-Directory $LocalTemp

    if (-not (Test-Path -LiteralPath $CompressSrc)) {
        Write-Status 'Creating compressible source payload (robocopy /compress)' 'Yellow'
        ('ABC' * 500000) | Out-File -FilePath $CompressSrc -Encoding ascii
    }

    # Seed data files for read/write loops (512 MB each)
    foreach ($seed in @($RandomDat, $SeqDat, $ReadDat, $LockFile)) {
        if (-not (Test-Path -LiteralPath $seed)) {
            Write-Status "Seeding $(Split-Path $seed -Leaf) on share..." 'Yellow'
            $fs = [System.IO.File]::Open($seed, [IO.FileMode]::Create, [IO.FileAccess]::Write, [IO.FileShare]::Read)
            try {
                $buf = New-Object byte[] 1048576
                (New-Object Random).NextBytes($buf)
                for ($i = 0; $i -lt 512; $i++) { [void]$fs.Write($buf, 0, $buf.Length) }
            }
            finally { $fs.Close() }
        }
    }

    # Directory tree for QUERY_DIRECTORY / READDIR-style traffic
    1..8 | ForEach-Object {
        $d = Join-Path $TraverseDir ("branch_{0:D2}" -f $_)
        Ensure-Directory $d
        1..20 | ForEach-Object {
            $f = Join-Path $d ("leaf_{0:D3}.bin" -f $_)
            if (-not (Test-Path -LiteralPath $f)) {
                [System.IO.File]::WriteAllBytes($f, (New-Object byte[] 4096))
            }
        }
    }
}

function Test-ShareReachable {
    if (-not (Test-Path -LiteralPath $NasShare)) {
        throw "SMB share not reachable: $NasShare"
    }
}

function Stop-AllWorkers {
    Write-Status 'Stopping workers...' 'Yellow'

    foreach ($job in $script:WorkerJobs) {
        if ($job) {
            Stop-Job -Job $job -ErrorAction SilentlyContinue
            Remove-Job -Job $job -Force -ErrorAction SilentlyContinue
        }
    }
    $script:WorkerJobs = @()
}

function Invoke-PeriodicCleanup {
    # Prevent unbounded growth while staying continuous
    Get-ChildItem -LiteralPath $MetaDir -Filter 'meta_*.txt' -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime |
        Select-Object -SkipLast 500 |
        Remove-Item -Force -ErrorAction SilentlyContinue
}

function Start-DiskspdLoop {
    param(
        [string] $Label,
        [string] $Args,
        [int]    $DurationSec = 45
    )
    if (-not (Test-Path -LiteralPath $DiskspdPath)) { return $null }

    $block = {
        param($Exe, $ArgLine, $Dur)
        while ($true) {
            $p = Start-Process -FilePath $Exe -ArgumentList $ArgLine -PassThru -WindowStyle Hidden
            $deadline = (Get-Date).AddSeconds($Dur)
            while (-not $p.HasExited -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 500 }
            if (-not $p.HasExited) { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue }
            Start-Sleep -Seconds 2
        }
    }

    return Start-Job -Name $Label -ScriptBlock $block -ArgumentList $DiskspdPath, $Args, $DurationSec
}

function Start-DotNetIoLoop {
    param(
        [string] $Name,
        [ValidateSet('Read', 'Write', 'Random')]
        [string] $Mode,
        [int]    $BlockSize = 65536,
        [string] $TargetFile
    )

    $block = {
        param($Mode, $BlockSize, $Target)
        $rng = New-Object Random
        $buf = New-Object byte[] $BlockSize
        while ($true) {
            try {
                switch ($Mode) {
                    'Read' {
                        $fs = [System.IO.File]::Open($Target, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)
                        $offset = [int64]($rng.NextDouble() * [Math]::Max(1, ($fs.Length - $BlockSize)))
                        $fs.Seek($offset, [IO.SeekOrigin]::Begin) | Out-Null
                        [void]$fs.Read($buf, 0, $BlockSize)
                        $fs.Close()
                    }
                    'Write' {
                        $fs = [System.IO.File]::Open($Target, [IO.FileMode]::Open, [IO.FileAccess]::Write, [IO.FileShare]::ReadWrite)
                        $offset = [int64]($rng.NextDouble() * [Math]::Max(1, ($fs.Length - $BlockSize)))
                        $fs.Seek($offset, [IO.SeekOrigin]::Begin) | Out-Null
                        $rng.NextBytes($buf)
                        [void]$fs.Write($buf, 0, $BlockSize)
                        $fs.Close()
                    }
                    'Random' {
                        if ($rng.NextDouble() -lt 0.35) {
                            $fs = [System.IO.File]::Open($Target, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)
                            [void]$fs.Read($buf, 0, [Math]::Min($BlockSize, 8192))
                        }
                        else {
                            $fs = [System.IO.File]::Open($Target, [IO.FileMode]::Open, [IO.FileAccess]::Write, [IO.FileShare]::ReadWrite)
                            $rng.NextBytes($buf)
                            [void]$fs.Write($buf, 0, 8192)
                        }
                        $fs.Close()
                    }
                }
            }
            catch { Start-Sleep -Milliseconds 50 }
        }
    }

    return Start-Job -Name $Name -ScriptBlock $block -ArgumentList $Mode, $BlockSize, $TargetFile
}

function Start-MetadataWorker {
    param([int] $WorkerId, [string] $Folder)

    $block = {
        param($Folder, $WorkerId)
        $n = 0
        while ($true) {
            $n++
            $batch = Join-Path $Folder ("batch_{0}_{1}" -f $WorkerId, ($n % 20))
            New-Item -ItemType Directory -Path $batch -Force | Out-Null
            1..40 | ForEach-Object {
                $target = Join-Path $batch ("meta_{0}_{1}.txt" -f $WorkerId, $_)
                [System.IO.File]::WriteAllText($target, ('x' * 256))
                if ($_ % 5 -eq 0) {
                    $renamed = Join-Path $batch ("ren_{0}_{1}.txt" -f $WorkerId, $_)
                    [System.IO.File]::Move($target, $renamed)
                }
            }
            Get-ChildItem -LiteralPath $batch -ErrorAction SilentlyContinue | Out-Null
            Remove-Item -LiteralPath $batch -Recurse -Force -ErrorAction SilentlyContinue
            Start-Sleep -Milliseconds (100 + ($WorkerId * 25))
        }
    }

    return Start-Job -Name "Meta_$WorkerId" -ScriptBlock $block -ArgumentList $Folder, $WorkerId
}

function Start-DirectoryTraverseWorker {
    param(
        [string] $Root,
        [int]    $WorkerId = 1
    )

    $block = {
        param($Root)
        while ($true) {
            Get-ChildItem -LiteralPath $Root -Recurse -Force -ErrorAction SilentlyContinue |
                Select-Object -ExpandProperty FullName | Out-Null
            Get-ChildItem -LiteralPath $Root -Directory -Recurse -ErrorAction SilentlyContinue |
                ForEach-Object { $_.GetFiles() | Out-Null }
            Start-Sleep -Milliseconds 300
        }
    }

    return Start-Job -Name ("DirTraverse_{0}" -f $WorkerId) -ScriptBlock $block -ArgumentList $Root
}

function Start-AttributeChurnWorker {
    param([string] $Folder)

    $block = {
        param($Folder)
        while ($true) {
            $f = Join-Path $Folder ('attr_{0}.tmp' -f ([guid]::NewGuid().ToString('N').Substring(0, 8)))
            [System.IO.File]::WriteAllText($f, 'attr churn')
            $item = Get-Item -LiteralPath $f
            $item.LastWriteTime = Get-Date
            $item.IsReadOnly = ((Get-Random -Maximum 2) -eq 0)
            $item.Attributes = 'Archive'
            Remove-Item -LiteralPath $f -Force -ErrorAction SilentlyContinue
            Start-Sleep -Milliseconds 150
        }
    }

    return Start-Job -Name 'AttrChurn' -ScriptBlock $block -ArgumentList $Folder
}

function Start-LockContentionWorker {
    param([string] $FilePath)

    $block = {
        param($FilePath)
        while ($true) {
            try {
                $fs = [System.IO.File]::Open(
                    $FilePath,
                    [IO.FileMode]::OpenOrCreate,
                    [IO.FileAccess]::ReadWrite,
                    [IO.FileShare]::None
                )
                Start-Sleep -Milliseconds (Get-Random -Minimum 20 -Maximum 120)
                $fs.Close()
            }
            catch { Start-Sleep -Milliseconds 30 }
        }
    }

    return Start-Job -Name 'LockStress' -ScriptBlock $block -ArgumentList $FilePath
}

function Start-CompressionWorker {
    param([string] $Src, [string] $DstFolder)

    $block = {
        param($Src, $DstFolder)
        $leaf = Split-Path $Src -Leaf
        while ($true) {
            $destName = 'compressible_{0}.txt' -f ([guid]::NewGuid().ToString('N').Substring(0, 8))
            robocopy (Split-Path $Src -Parent) $DstFolder $leaf /compress /mt:4 /R:1 /W:1 /NFL /NDL /NJH /NJS |
                Out-Null
            $copied = Join-Path $DstFolder $leaf
            if (Test-Path -LiteralPath $copied) {
                Rename-Item -LiteralPath $copied -NewName $destName -Force -ErrorAction SilentlyContinue
                $final = Join-Path $DstFolder $destName
                if (Test-Path -LiteralPath $final) {
                    Remove-Item -LiteralPath $final -Force -ErrorAction SilentlyContinue
                }
            }
            Start-Sleep -Seconds 30
        }
    }

    return Start-Job -Name 'Compress' -ScriptBlock $block -ArgumentList $Src, $DstFolder
}

function Start-AllWorkloads {
    $useDiskspd = Test-Path -LiteralPath $DiskspdPath
    if ($useDiskspd) {
        Write-Status "Using diskspd at $DiskspdPath" 'Green'
        $script:WorkerJobs += Start-DiskspdLoop -Label 'DiskspdRandom' -Args "-b8K -d45 -o8 -t8 -r -w35 -c1G -h -L `"$RandomDat`""
        $script:WorkerJobs += Start-DiskspdLoop -Label 'DiskspdSeqWrite' -Args "-b64K -d45 -o4 -t4 -w100 -c1G -h -L `"$SeqDat`""
        $script:WorkerJobs += Start-DiskspdLoop -Label 'DiskspdSeqRead' -Args "-b64K -d45 -o4 -t4 -r -w0 -c1G -h -L `"$ReadDat`""
    }
    else {
        Write-Status 'diskspd not found — using .NET I/O loops' 'Yellow'
        $script:WorkerJobs += Start-DotNetIoLoop -Name 'NetRandom' -Mode 'Random' -BlockSize 8192  -TargetFile $RandomDat
        $script:WorkerJobs += Start-DotNetIoLoop -Name 'NetWrite'  -Mode 'Write'  -BlockSize 65536 -TargetFile $SeqDat
        $script:WorkerJobs += Start-DotNetIoLoop -Name 'NetRead'   -Mode 'Read'   -BlockSize 65536 -TargetFile $ReadDat
    }

    1..$MetaWorkers | ForEach-Object {
        $script:WorkerJobs += Start-MetadataWorker -WorkerId $_ -Folder $MetaDir
    }
    1..$DirWorkers | ForEach-Object {
        $script:WorkerJobs += Start-DirectoryTraverseWorker -Root $TraverseDir -WorkerId $_
    }

    $script:WorkerJobs += Start-AttributeChurnWorker -Folder $MetaDir
    $script:WorkerJobs += Start-LockContentionWorker -FilePath $LockFile
    $script:WorkerJobs += Start-CompressionWorker -Src $CompressSrc -DstFolder $DataDir

    Write-Status ("Started {0} background workers" -f $script:WorkerJobs.Count) 'Green'
}

# ── Main ─────────────────────────────────────────────────────────────────────
try {
    Write-Host ''
    Write-Host '======================================================================' -ForegroundColor Cyan
    Write-Host ' vast-opstat SMB Continuous Load Generator' -ForegroundColor Cyan
    Write-Host '======================================================================' -ForegroundColor Cyan
    Write-Host " Share:      $NasShare"
    Write-Host " Test root:  $TestRoot"
    Write-Host " Phase rot:  every ${PhaseSeconds}s (bias label for operator)"
    Write-Host ''
    Write-Host ' TUI mapping:' -ForegroundColor DarkCyan
    Write-Host '   READ/WRITE panels  <- diskspd or .NET random/seq I/O'
    Write-Host '   Metadata panel     <- create/delete/rename + dir listing'
    Write-Host '   Health mix bars    <- metadata workers vs data I/O'
    Write-Host '   View drill (v)     <- all traffic under this share path'
    Write-Host ''
    Write-Host ' Press Ctrl+C to stop.' -ForegroundColor Yellow
    Write-Host '======================================================================' -ForegroundColor Cyan

    Test-ShareReachable
    Initialize-TestLayout
    Start-AllWorkloads

    $phaseStarted = Get-Date
    while ($true) {
        if (((Get-Date) - $phaseStarted).TotalSeconds -ge $PhaseSeconds) {
            $script:PhaseIndex = ($script:PhaseIndex + 1) % $script:PhaseNames.Count
            $phaseStarted = Get-Date
            Write-Status ("Phase emphasis: {0}" -f $script:PhaseNames[$script:PhaseIndex]) 'Cyan'
        }

        $alive = @($script:WorkerJobs | Where-Object { $_.State -eq 'Running' }).Count
        Write-Status ("Workers running: {0}/{1} | phase: {2}" -f $alive, $script:WorkerJobs.Count, $script:PhaseNames[$script:PhaseIndex]) 'DarkGray'
        Invoke-PeriodicCleanup
        Start-Sleep -Seconds 15
    }
}
catch [System.Management.Automation.PipelineStoppedException] {
    # Ctrl+C
}
catch {
    Write-Status $_.Exception.Message 'Red'
    exit 1
}
finally {
    Stop-AllWorkers
    Write-Status 'Stopped. Test files remain on share for inspection; re-run to continue load.' 'Green'
}
