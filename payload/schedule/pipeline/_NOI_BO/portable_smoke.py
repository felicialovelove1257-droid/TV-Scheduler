import sys,subprocess,tempfile,json
from pathlib import Path
import tkinter as tk
import episode_scanner,schedule_engine,create_episode
root=tk.Tk();root.withdraw();root.update_idletasks();root.destroy()
base=Path(__file__).resolve().parent
with tempfile.TemporaryDirectory() as td:
 p=Path(td)/'test.mp4'
 subprocess.run([str(base/'runtime/ffmpeg/ffmpeg.exe'),'-v','error','-f','lavfi','-i','anullsrc=r=48000:cl=stereo','-t','1','-c:a','aac',str(p)],check=True,creationflags=subprocess.CREATE_NO_WINDOW)
 data=subprocess.check_output([str(base/'runtime/ffmpeg/ffprobe.exe'),'-v','error','-show_entries','format=duration','-of','json',str(p)],creationflags=subprocess.CREATE_NO_WINDOW)
 assert abs(float(json.loads(data)['format']['duration'])-1)<.1
print('Python:',sys.executable)
print('Tkinter GUI, pipeline imports, FFmpeg encode, FFprobe duration: OK')
