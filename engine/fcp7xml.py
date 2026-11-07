#!/usr/bin/env python3
"""Edit list (JSON) -> Final Cut Pro 7 XML (xmeml v5) that Premiere Pro imports (File > Import).
fcp7xml.py <edit.json> <out.xml>
edit.json: {"name": "Wk07 Highlights", "fps": 59.94, "w": 1920, "h": 1080,
            "files": {"master": {"path": "/path/to/master.mp4", "dur": 10526.5, "audio_ch": 2}},
            "items": [{"file": "master", "in": 1182.0, "out": 1196.5, "label": "Q1 11:42 ..."}],   # V1/A1-2, back to back
            "music": [{"path": "/path/to/music.mp3", "dur": 180.0, "at": 0.0, "in": 0.0, "out": 120.0, "gain_db": -12}],
            "markers": [{"at": 12.3, "name": "TD"}]}
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
        v.append(f'<clipitem id="v{n}">{common}{fileel(it["file"])}{link}</clipitem>')
        for lst, ch, side in ((a1, 1, 'l'), (a2, 2, 'r')):
            lst.append(f'<clipitem id="a{n}{side}">{common}<file id="file-{esc(it["file"])}"/>'
                       f'<sourcetrack><mediatype>audio</mediatype><trackindex>{ch}</trackindex></sourcetrack>{link}</clipitem>')
        pos += d
    total = pos
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
            f'<pixelaspectratio>square</pixelaspectratio></samplecharacteristics></format>{tr(v)}</video>'
            f'<audio><numOutputChannels>2</numOutputChannels>{audio_tracks}</audio></media></sequence></xmeml>\n')


if __name__ == '__main__':
    E = json.load(open(sys.argv[1]))
    open(sys.argv[2], 'w').write(build(E))
    print('wrote', sys.argv[2], len(E['items']), 'clips')
