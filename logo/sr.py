"""x4 AI super-resolution (EDSR) — run with srenv/bin/python (opencv-contrib 4.x). sr.py in.png out.png"""
import sys, os, cv2
here = os.path.dirname(os.path.abspath(__file__))
sr = cv2.dnn_superres.DnnSuperResImpl_create()
img = cv2.imread(sys.argv[1])
big = max(img.shape[:2]) > 600
sr.readModel(os.path.join(here, '..', 'resources', 'models', 'FSRCNN_x4.pb' if big else 'EDSR_x4.pb'))
sr.setModel('fsrcnn' if big else 'edsr', 4)
cv2.imwrite(sys.argv[2], sr.upsample(img))
