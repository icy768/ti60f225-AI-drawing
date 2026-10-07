@echo off
rem Build StyleCam firmware: sequence header -> make -> on-chip RAM images (ip\soc, fw_rom)
setlocal
call D:\yilinsiFPGA\bin\efx_env.bat >nul
cd /d %~dp0
set BSP=efinix/EfxSapphireSoc
python tools.py gen_seq || exit /b 1
python tools.py gen_blob || exit /b 1
make -s all || exit /b 1
python tools.py mkrom || exit /b 1
endlocal
