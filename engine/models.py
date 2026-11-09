"""models.py - where the big downloaded models live (rembg's BiRefNet / U^2-Net ONNX files).

rembg_home() picks the folder once, before rembg is imported, and exports it as $U2NET_HOME:
  1. $U2NET_HOME if it is already set;
  2. "rembg_models" in this machine's local.json (repo root; not committed), e.g. a shared network drive;
  3. resources/models/rembg in the engine folder, when it exists;
  4. otherwise rembg's own default folder. rembg downloads a missing model there on first use.
"""
import json, os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def rembg_home():
    if os.environ.get("U2NET_HOME"):
        return os.environ["U2NET_HOME"]
    try:
        d = json.load(open(os.path.join(REPO, "local.json"))).get("rembg_models")
    except (OSError, ValueError):
        d = None
    if d:
        try:
            os.makedirs(d, exist_ok=True)       # a named folder that doesn't exist yet is created (rembg fills it)
        except OSError:
            d = None
    if not d or not os.path.isdir(d):
        d = os.path.join(REPO, "resources", "models", "rembg")
    if os.path.isdir(d):
        os.environ["U2NET_HOME"] = d
        return d
    return None
