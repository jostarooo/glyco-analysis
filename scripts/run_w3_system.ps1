param(
    [ValidateSet("serve", "doctor")]
    [string]$Command = "serve",
    [string]$HostAddress = "127.0.0.1",
    [int]$Port = 8765,
    [switch]$Preload
)

$repo = "D:\wbworkspace\glyco-analysis"
$python = "C:\Users\jostaro\AppData\Roaming\uv\python\cpython-3.12.14-windows-x86_64-none\python.exe"

$env:PYTHONPATH = "$repo;$repo\.venv\Lib\site-packages"
$env:PYTHONUTF8 = "1"
$env:HF_HOME = "D:\hf"
$env:HF_HUB_CACHE = "D:\hf\hub"
$env:HF_HUB_OFFLINE = "1"
$env:TRANSFORMERS_OFFLINE = "1"
$env:LORA_N_GLY_COMPAT_PATH = "D:\uv\pylibs\lora-n-gly-peft014"
$env:GLYCO_COMPAT_PATH = $env:LORA_N_GLY_COMPAT_PATH

$arguments = @("-m", "system", $Command)
if ($Command -eq "serve") {
    $arguments += @("--host", $HostAddress, "--port", "$Port")
}
if ($Preload.IsPresent) {
    $arguments += "--preload"
}

& $python @arguments
exit $LASTEXITCODE
