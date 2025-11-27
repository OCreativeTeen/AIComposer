# look for typical CUDA locations
$paths = @(
  "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA",
  "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.8",
  "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\*"
)
Get-ChildItem -Directory $paths -ErrorAction SilentlyContinue | ForEach-Object {
  $bin = Join-Path $_.FullName "bin"
  if (Test-Path $bin) {
    Write-Output "$bin ->" (Test-Path (Join-Path $bin "cudart64_128.dll"))
  }
}
# also try where nvcc (if in PATH)
where.exe nvcc 2>$null
