#!/bin/sh
# Actual FPGA regression; every failed trial stops this sequence.
set -eu
launcher=/tmp/rasterix-games/runtime/bin/rix-games
logs=/tmp/postproc-tests
grep -q '"passed": true' /tmp/rasterix-games/results/glx_final03/result.json
for n in 02 03 04; do
    "$launcher" glx-probe --attempt glx_mix$n --seconds 8 --fresh-profile --filter nearest >"$logs/games-glx_mix$n.log" 2>&1
done
chmod +x /tmp/cache-qa
export DISPLAY=:0 SDL_VIDEODRIVER=x11 SDL_AUDIODRIVER=dummy
export LD_LIBRARY_PATH=/tmp/rasterix-games/runtime/lib
export SDL_VIDEO_GL_DRIVER=/tmp/rasterix-games/runtime/lib/libGL.so.1
RIX_VERTEX_CACHE=1 /tmp/cache-qa "$logs/cache-on.bin" >"$logs/cache-on.log" 2>&1
RIX_VERTEX_CACHE=0 /tmp/cache-qa "$logs/cache-off.bin" >"$logs/cache-off.log" 2>&1
python3 - <<'PY'
import hashlib,json,pathlib,subprocess
base=pathlib.Path('/tmp/postproc-tests')
a=(base/'cache-on.bin').read_bytes();b=(base/'cache-off.bin').read_bytes()
unique=len(set(a[i:i+3] for i in range(0,len(a),4)))
lit=sum(a[i:i+3]!=b'\0\0\0' for i in range(0,len(a),4))
result={'bytes':len(a),'pixels':len(a)//4,'identical':a==b,'sha256':hashlib.sha256(a).hexdigest(),
        'unique_colors':unique,'nonblack_pixels':lit,'indices':4608,'source_and_transform_changed':True,
        'logs':{n:(base/(n+'.log')).read_text() for n in ('cache-on','cache-off')},
        'status':json.loads(subprocess.check_output(['plgpuctl','status']))}
result['passed']=len(a)==384000 and a==b and unique>100 and lit>30000 and all('gl_error=0' in log for log in result['logs'].values())
(base/'games-cache-qa.json').write_text(json.dumps(result,indent=2)+'\n')
assert result['passed'],result
PY
unset LD_LIBRARY_PATH SDL_VIDEO_GL_DRIVER
"$launcher" neverball --attempt ball_final03 --seconds 60 --fresh-profile --autoplay --filter nearest --capture >"$logs/games-ball_final03.log" 2>&1
"$launcher" neverputt --attempt putt_final03 --seconds 50 --fresh-profile --autoplay --filter nearest --capture >"$logs/games-putt_final03.log" 2>&1
"$launcher" quake --attempt quake_final03 --seconds 50 --fresh-profile --filter nearest --capture >"$logs/games-quake_final03.log" 2>&1
"$launcher" quake3 --attempt q3_final03 --seconds 50 --fresh-profile --filter nearest --capture >"$logs/games-q3_final03.log" 2>&1
"$launcher" tuxracer --attempt tux_final03 --seconds 150 --fresh-profile --autoplay --filter nearest --capture >"$logs/games-tux_final03.log" 2>&1
echo GAME_OPTIMIZATION_SUITE_PASS
