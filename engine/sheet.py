#!/usr/bin/env python3
"""Contact sheet for review: sheet.py <video> <out.jpg> <t0> <t1> [--n 12] [--cols 6] [--w 320] [--label TEXT]
Frames evenly from t0..t1 (seconds in <video>), each labeled with its time. Runs wherever ffmpeg is."""
import sys, subprocess, tempfile, os
import numpy as np, cv2


def main():
    a = sys.argv
    if len(a) < 5 or '-h' in a or '--help' in a:
        print(__doc__.strip()); sys.exit(0 if ('-h' in a or '--help' in a) else 2)
    v, out, t0, t1 = a[1], a[2], float(a[3]), float(a[4])
    n = int(a[a.index('--n') + 1]) if '--n' in a else 12
    cols = int(a[a.index('--cols') + 1]) if '--cols' in a else 6
    W = int(a[a.index('--w') + 1]) if '--w' in a else 320
    label = a[a.index('--label') + 1] if '--label' in a else ''
    ts = np.linspace(t0, t1, n)
    tiles = []
    with tempfile.TemporaryDirectory() as tmp:
        for i, t in enumerate(ts):
            p = f'{tmp}/{i}.jpg'
            subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-ss', f'{t:.2f}', '-i', v, '-frames:v', '1',
                            '-vf', f'scale={W}:-2', p], stdin=subprocess.DEVNULL)
            im = cv2.imread(p)
            if im is None:
                im = np.zeros((W * 9 // 16, W, 3), np.uint8)
            cv2.rectangle(im, (0, 0), (110, 22), (0, 0, 0), -1)
            cv2.putText(im, f'{t:.1f}s', (4, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            tiles.append(im)
    h = tiles[0].shape[0]
    tiles = [cv2.resize(t, (W, h)) for t in tiles]
    while len(tiles) % cols:
        tiles.append(np.zeros_like(tiles[0]))
    rows = [np.hstack(tiles[r * cols:(r + 1) * cols]) for r in range(len(tiles) // cols)]
    sheet = np.vstack(rows)
    if label:
        bar = np.zeros((30, sheet.shape[1], 3), np.uint8)
        cv2.putText(bar, label, (8, 21), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
        sheet = np.vstack([bar, sheet])
    cv2.imwrite(out, sheet, [cv2.IMWRITE_JPEG_QUALITY, 82])


if __name__ == '__main__':
    main()
