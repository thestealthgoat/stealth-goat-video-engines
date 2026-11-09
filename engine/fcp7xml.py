#!/usr/bin/env python3
"""Edit list (JSON) -> Final Cut Pro 7 XML (xmeml v5) that Premiere Pro imports (File > Import).
fcp7xml.py <edit.json> <out.xml>
fcp7xml.py --single <render.mp4> [out.xml] [--path <path Premiere sees>]   one finished render as a one-clip sequence
                                    (its own size, rate and audio), for tools that only write an MP4
edit.json: {"name": "Wk07 Highlights", "fps": 59.94, "w": 1920, "h": 1080,
            "files": {"master": {"path": "/path/to/master.mp4", "dur": 10526.5, "audio_ch": 2}},
            "items": [{"file": "master", "in": 1182.0, "out": 1196.5, "label": "Q1 11:42 ..."}],   # V1/A1-2, back to back
            "music": [{"path": "/path/to/music.mp3", "dur": 180.0, "at": 0.0, "in": 0.0, "out": 120.0, "gain_db": -12}],
            "markers": [{"at": 12.3, "name": "TD"}],
            "overlays": [{"path": "/path/to/card.mp4", "dur": 1.6, "at": 20.0, "in": 0, "out": 1.6, "label": "card"}]}
Optional per item: "scale": 108 (Basic Motion scale in percent, about the frame center).
"overlays": video-only clips on V2 above the cut (title cards, a caption layer), placed at "at" seconds.
Paths are data: they are written as given, so they must be the paths Premiere will see on the editing machine
(e.g. the shared drive's mount point), not the paths of the machine that runs this script.
"""
import sys, json, html, urllib.parse


def tb(fps):
    if abs(fps - 59.94) < 0.01:
        return 60, True
    if abs(fps - 29.97) < 0.01:
        return 30, True
    if abs(fps - 23.976) < 0.01:
        return 24, True
    return int(round(fps)), False


def fr(sec, fps):
    return int(round(sec * fps))


def url(p):
    return 'file://localhost' + urllib.parse.quote(p)


def rate(fps):
    b, n = tb(fps)
    return f'<rate><timebase>{b}</timebase><ntsc>{"TRUE" if n else "FALSE"}</ntsc></rate>'


def motion(scale):
    """Basic Motion scale (percent) for a video clipitem; nothing at 100 %."""
    if scale is None or abs(float(scale) - 100) < 1e-6:
        return ''
    return ('<filter><effect><name>Basic Motion</name><effectid>basic</effectid><effectcategory>motion</effectcategory>'
            '<effecttype>motion</effecttype><mediatype>video</mediatype><parameter authoringApp="PremierePro">'
            '<parameterid>scale</parameterid><name>Scale</name><valuemin>0</valuemin><valuemax>1000</valuemax>'
            f'<value>{float(scale):g}</value></parameter></effect></filter>')


def build(E):
    fps = E.get('fps', 59.94); W, H = E.get('w', 1920), E.get('h', 1080)
    R = rate(fps); esc = html.escape
    files = E['files']; seen = set()

    def fileel(key, kind='av'):
        f = files[key]
        if key in seen:
            return f'<file id="file-{esc(key)}"/>'
        seen.add(key)
        name = f['path'].rsplit('/', 1)[-1]
        media = ''
        if kind in ('av', 'v'):
            media += (f'<video><samplecharacteristics>{R}<width>{W}</width><height>{H}</height>'
                      f'<pixelaspectratio>square</pixelaspectratio></samplecharacteristics></video>')
        if kind in ('av', 'a'):
            media += (f'<audio><samplecharacteristics><depth>16</depth><samplerate>48000</samplerate></samplecharacteristics>'
                      f'<channelcount>{f.get("audio_ch", 2)}</channelcount></audio>')
        return (f'<file id="file-{esc(key)}"><name>{esc(name)}</name><pathurl>{url(f["path"])}</pathurl>{R}'
                f'<duration>{fr(f["dur"], fps)}</duration><media>{media}</media></file>')

    v, a1, a2 = [], [], []
    pos = 0; n = 0
    for it in E['items']:
        n += 1
        i, o = fr(it['in'], fps), fr(it['out'], fps)
        d = o - i
        lab = esc(it.get('label', f'clip {n}'))
        common = f'<name>{lab}</name><enabled>TRUE</enabled><duration>{fr(files[it["file"]]["dur"], fps)}</duration>{R}' \
                 f'<start>{pos}</start><end>{pos + d}</end><in>{i}</in><out>{o}</out>'
        link = (f'<link><linkclipref>v{n}</linkclipref><mediatype>video</mediatype><trackindex>1</trackindex><clipindex>{n}</clipindex></link>'
                f'<link><linkclipref>a{n}l</linkclipref><mediatype>audio</mediatype><trackindex>1</trackindex><clipindex>{n}</clipindex><groupindex>1</groupindex></link>'
                f'<link><linkclipref>a{n}r</linkclipref><mediatype>audio</mediatype><trackindex>2</trackindex><clipindex>{n}</clipindex><groupindex>1</groupindex></link>')
        silent = files[it["file"]].get("audio_ch", 2) == 0       # a render with no audio stream: picture only
        if silent:
            link = ''
        v.append(f'<clipitem id="v{n}">{common}{fileel(it["file"], "v" if silent else "av")}{motion(it.get("scale"))}{link}</clipitem>')
        for lst, ch, side in (() if silent else ((a1, 1, 'l'), (a2, 2, 'r'))):
            lst.append(f'<clipitem id="a{n}{side}">{common}<file id="file-{esc(it["file"])}"/>'
                       f'<sourcetrack><mediatype>audio</mediatype><trackindex>{ch}</trackindex></sourcetrack>{link}</clipitem>')
        pos += d
    total = pos
    ov = []
    for o_i, o in enumerate(E.get('overlays', [])):
        key = f'ovl{o_i}'
        files[key] = {'path': o['path'], 'dur': o['dur']}
        s = fr(o.get('at', 0), fps); i = fr(o.get('in', 0), fps); o_ = fr(o.get('out', o['dur']), fps)
        ov.append(f'<clipitem id="o{o_i}"><name>{esc(o.get("label", o["path"].rsplit("/", 1)[-1]))}</name>'
                  f'<enabled>TRUE</enabled><duration>{fr(o["dur"], fps)}</duration>{R}<start>{s}</start>'
                  f'<end>{s + o_ - i}</end><in>{i}</in><out>{o_}</out>{fileel(key, "v")}</clipitem>')
    mus = []
    for m_i, m in enumerate(E.get('music', [])):
        key = f'music{m_i}'
        files[key] = {'path': m['path'], 'dur': m['dur'], 'audio_ch': 2}
        s = fr(m.get('at', 0), fps); i = fr(m.get('in', 0), fps); o = fr(m.get('out', m['dur']), fps)
        g = m.get('gain_db', 0)
        filt = (f'<filter><effect><name>Audio Levels</name><effectid>audiolevels</effectid><effecttype>audiolevels</effecttype>'
                f'<mediatype>audio</mediatype><parameter><parameterid>level</parameterid><name>Level</name>'
                f'<value>{10 ** (g / 20):.4f}</value></parameter></effect></filter>') if g else ''
        for ch in (1, 2):
            fe = fileel(key, 'a') if ch == 1 else f'<file id="file-{key}"/>'
            mus.append((ch, f'<clipitem id="m{m_i}_{ch}"><name>{esc(m["path"].rsplit("/", 1)[-1])}</name><enabled>TRUE</enabled>'
                            f'<duration>{fr(m["dur"], fps)}</duration>{R}<start>{s}</start><end>{s + o - i}</end><in>{i}</in><out>{o}</out>'
                            f'{fe}<sourcetrack><mediatype>audio</mediatype><trackindex>{ch}</trackindex></sourcetrack>{filt}</clipitem>'))
    marks = ''.join(f'<marker><name>{esc(m["name"])}</name><in>{fr(m["at"], fps)}</in><out>-1</out></marker>'
                    for m in E.get('markers', []))
    tr = lambda items: f'<track>{"".join(items)}<enabled>TRUE</enabled></track>'
    audio_tracks = tr(a1) + tr(a2)
    if mus:
        audio_tracks += tr([x for c, x in mus if c == 1]) + tr([x for c, x in mus if c == 2])
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xmeml>\n<xmeml version="5"><sequence id="seq-1">'
            f'<name>{esc(E.get("name", "Sequence"))}</name><duration>{total}</duration>{R}'
            f'<timecode>{R}<string>00:00:00:00</string><frame>0</frame><displayformat>NDF</displayformat></timecode>'
            f'{marks}<media><video><format><samplecharacteristics>{R}<width>{W}</width><height>{H}</height>'
            f'<pixelaspectratio>square</pixelaspectratio></samplecharacteristics></format>{tr(v)}{tr(ov) if ov else ""}</video>'
            f'<audio><numOutputChannels>2</numOutputChannels>{audio_tracks}</audio></media></sequence></xmeml>\n')


def single(mp4, path=None):
    """an edit list for one finished render: its own size, frame rate and audio channels (ffprobe)"""
    import subprocess
    pr = json.loads(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'stream=codec_type,width,height,r_frame_rate,channels:format=duration',
                                    '-of', 'json', mp4], capture_output=True, text=True, check=True).stdout)
    v = next(s for s in pr['streams'] if s['codec_type'] == 'video'); a = [s for s in pr['streams'] if s['codec_type'] == 'audio']
    n, d = (int(x) for x in v['r_frame_rate'].split('/')); fps = n / d; dur = float(pr['format']['duration'])
    name = mp4.rsplit('/', 1)[-1].rsplit('.', 1)[0]
    return {'name': name, 'fps': round(fps, 3), 'w': int(v['width']), 'h': int(v['height']),
            'files': {'r': {'path': path or __import__('os').path.abspath(mp4), 'dur': dur, 'audio_ch': a[0].get('channels', 2) if a else 0}},
            'items': [{'file': 'r', 'in': 0.0, 'out': int(dur * fps + 1e-6) / fps, 'label': name}]}


if __name__ == '__main__':
    if len(sys.argv) < 2 or sys.argv[1] in ('-h', '--help'):
        print(__doc__); sys.exit(0)
    if sys.argv[1] == '--single':
        args = sys.argv[2:]; path = None
        if '--path' in args:
            i = args.index('--path'); path = args[i + 1]; del args[i:i + 2]
        mp4 = args[0]; out = args[1] if len(args) > 1 else mp4.rsplit('.', 1)[0] + '.xml'
        open(out, 'w').write(build(single(mp4, path)))
        print('wrote', out)
        sys.exit(0)
    E = json.load(open(sys.argv[1]))
    open(sys.argv[2], 'w').write(build(E))
    print('wrote', sys.argv[2], len(E['items']), 'clips')
