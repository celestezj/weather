[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

# ===== HTTP 服务端口，改这里即可 =====
$httpPort = 8055

$weatherArgs = @('weather.py','--days','7','--hours','24','--output','weather_data.json','--watch','30');
$procWeather = Start-Process python -ArgumentList $weatherArgs -NoNewWindow -PassThru;
$procHttp = Start-Process python -ArgumentList '-m','http.server',"$httpPort" -NoNewWindow -PassThru;

Write-Host '============================================';
Write-Host ("[START] weather.py name:" + $procWeather.Name + "  PID:" + $procWeather.Id);
Write-Host ("[START] http.server name:" + $procHttp.Name + "  PID:" + $procHttp.Id);
Write-Host '============================================';

Start-Process "http://localhost:$httpPort/weather.html";

try {
    Write-Host 'Services running, press Ctrl+C to stop all services';
    while(-not ($procWeather.HasExited -or $procHttp.HasExited)){ Start-Sleep -Milliseconds 300 }
    Write-Host '[Child process exited, start cleanup]';
}
finally {
    Write-Host '';
    Write-Host '>>>>>>>>>> ENTER CLEANUP <<<<<<<<<<';

    if(-not $procWeather.HasExited) {
        Write-Host ("Killing weather.py PID=" + $procWeather.Id);
        $procWeather.Kill();
        $procWeather.WaitForExit();
        Write-Host ("weather.py PID=" + $procWeather.Id + "  HasExited:" + $procWeather.HasExited);
    } else {
        Write-Host ("weather.py PID=" + $procWeather.Id + " already exited");
    }

    if(-not $procHttp.HasExited) {
        Write-Host ("Killing http.server PID=" + $procHttp.Id);
        $procHttp.Kill();
        $procHttp.WaitForExit();
        Write-Host ("http.server PID=" + $procHttp.Id + "  HasExited:" + $procHttp.HasExited);
    } else {
        Write-Host ("http.server PID=" + $procHttp.Id + " already exited");
    }

    Write-Host '>>>>>>>>>> CLEANUP DONE <<<<<<<<<<';
}