#!/usr/bin/env python3
"""Profiles: everything about one organization (brand, folders, house style) lives in profiles/<name>/profile.json.
Core tools never hard-code paths, colors, fonts or team names; they ask the profile.

Use from a tool:
    import vprofile as prof                    # engine/ is on sys.path (tools do this themselves)
    ap = argparse.ArgumentParser(); prof.add_arg(ap); a = ap.parse_args()
    P = prof.load(a.profile)                   # --profile, else $VIDEO_PROFILE, else local.json "default_profile"
    P.color("primary")        -> "#112233"     P.rgb("accent") -> (224, 64, 80)
    P.font("head")            -> absolute .ttf path
    P.path("music")           -> absolute folder (path map applied, so it works on the NAS, a laptop or the cloud)
    P.get("team.home_name")   -> "HAWKS"       P.get("delivery.loudness_lufs", -14)
    P.map_path(p)             -> a path from an edit list, rewritten for this machine

Values may use {repo} (this folder), {profile} (the profile's folder), {home} and any key under "paths"
(e.g. "{assets}/Music"). "path_map" is a list of ["/Volumes/ACME", "/mnt/acme"] pairs: a path
under the left side is rewritten to the right side only when the left side is missing and the right side exists.
"optional_paths" is a list of "paths" keys that only exist on some machines (e.g. a Dropbox folder under one
person's home): `show --check` lists them as "optional, missing here" when they are absent, without failing.

CLI:
    python3 engine/vprofile.py list
    python3 engine/vprofile.py show acme [--check]       # --check: every font and folder exists on this machine
                                                         #   (optional_paths missing here are listed, not failed)
    python3 engine/vprofile.py new <name> --primary "#123456" --accent "#ABCDEF" [--head-font F --body-font F]
                                  [--logo logo.svg] [--root /path/to/org] [--sample]   # --sample renders a test card
    python3 engine/vprofile.py default acme             # writes local.json (machine-only, not committed)
"""
import argparse, json, os, re, sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROFILES = os.path.join(REPO, "profiles")
LOCAL = os.path.join(REPO, "local.json")
_TOKEN = re.compile(r"\{([A-Za-z0-9_]+)\}")


class ProfileError(Exception):
    pass


def _local():
    try:
        with open(LOCAL) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def available():
    if not os.path.isdir(PROFILES):
        return []
    return sorted(d for d in os.listdir(PROFILES)
                  if not d.startswith((".", "_")) and os.path.isfile(os.path.join(PROFILES, d, "profile.json")))


def add_arg(ap, required=False):
    """Add --profile to an argparse parser."""
    ap.add_argument("--profile", required=required,
                    help="profile name or path to a profile.json (default: $VIDEO_PROFILE, then local.json)")
    return ap


class Profile:
    def __init__(self, data, folder):
        self.data = data
        self.folder = folder
        self.name = data.get("name") or os.path.basename(folder)
        self._paths = {}
        raw = data.get("paths", {})
        for k in raw:
            self._paths[k] = None
        for k in raw:                       # resolve in any order; tokens may refer to other paths
            self._resolve_key(k, raw, set())

    # ---- token expansion -------------------------------------------------------------------------------
    def _base_tokens(self):
        return {"repo": REPO, "profile": self.folder, "home": os.path.expanduser("~")}

    def _resolve_key(self, key, raw, seen):
        if self._paths.get(key) is not None:
            return self._paths[key]
        if key in seen:
            raise ProfileError(f"profile {self.name}: paths.{key} refers to itself")
        seen.add(key)
        val = self._expand(raw[key], raw, seen)
        self._paths[key] = self.map_path(val)
        return self._paths[key]

    def _expand(self, s, raw=None, seen=None):
        if not isinstance(s, str):
            return s
        raw = raw if raw is not None else self.data.get("paths", {})
        base = self._base_tokens()

        def sub(m):
            k = m.group(1)
            if k in base:
                return base[k]
            if k in raw:
                return self._resolve_key(k, raw, seen if seen is not None else set())
            raise ProfileError(f"profile {self.name}: unknown token {{{k}}} in {s!r}")
        out = _TOKEN.sub(sub, s)
        return os.path.expandvars(os.path.expanduser(out))

    # ---- public API ------------------------------------------------------------------------------------
    def get(self, dotted, default=KeyError):
        cur = self.data
        for part in dotted.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                if default is KeyError:
                    raise ProfileError(f"profile {self.name}: missing {dotted}")
                return default
        return cur

    def text(self, dotted, default=KeyError):
        """A string value with {tokens} expanded (for labels that mention the org, e.g. footer lines)."""
        v = self.get(dotted, default)
        return self._expand(v) if isinstance(v, str) and "{" in v else v

    def color(self, role):
        c = self.get(f"brand.colors.{role}")
        return c if c.startswith("#") else "#" + c

    def rgb(self, role):
        h = self.color(role).lstrip("#")
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))

    def font(self, role):
        p = self._expand(self.get(f"brand.fonts.{role}"))
        if not os.path.isabs(p):
            p = os.path.join(self.folder, p)
        return p

    def asset(self, dotted):
        """A file path stored anywhere in the profile (e.g. 'brand.logo_png'), expanded and path-mapped."""
        p = self._expand(self.get(dotted))
        if not os.path.isabs(p):
            p = os.path.join(self.folder, p)
        return self.map_path(p)

    def path(self, key):
        if key not in self._paths:
            raise ProfileError(f"profile {self.name}: no paths.{key} (have: {', '.join(sorted(self._paths))})")
        return self._paths[key]

    def has_path(self, key):
        return key in self._paths

    def map_path(self, p):
        if not isinstance(p, str):
            return p
        for pair in self.data.get("path_map", []):
            src, dst = pair[0].rstrip("/"), os.path.expandvars(os.path.expanduser(pair[1])).rstrip("/")
            if (p == src or p.startswith(src + "/")) and not os.path.exists(src) and os.path.exists(dst):
                return dst + p[len(src):]
        return p

    def optional_paths(self):
        """The "paths" keys the profile marks as machine-only (top-level "optional_paths" list)."""
        opt = self.data.get("optional_paths", [])
        if isinstance(opt, str):
            return {opt}                    # one key written without the list brackets
        return {k for k in opt if isinstance(k, str)} if isinstance(opt, list) else set()

    def check_optional(self):
        """Optional (machine-only) paths that are missing on this machine: reported, never a failure."""
        return [f"path {k}: {v}" for k, v in self._paths.items()
                if k in self.optional_paths() and not os.path.exists(v)]

    def check(self):
        """List of problems on this machine (missing fonts, folders, assets). Paths listed in "optional_paths"
        are not problems when missing (see check_optional()); a name there that is not a "paths" key is one."""
        bad = []
        for role in self.get("brand.fonts", {}):
            f = self.font(role)
            if not os.path.isfile(f):
                bad.append(f"font {role}: {f}")
        opt = self.optional_paths()
        raw_opt = self.data.get("optional_paths", [])
        if not isinstance(raw_opt, (list, str)) or (isinstance(raw_opt, list)
                                                    and not all(isinstance(k, str) for k in raw_opt)):
            bad.append(f"optional_paths should be a list of paths keys, e.g. [\"dropbox\"] (got {raw_opt!r})")
        for k in sorted(opt - set(self._paths)):
            bad.append(f"optional_paths names {k!r}, which is not a paths key (have: {', '.join(sorted(self._paths))})")
        for k, v in self._paths.items():
            if k in opt:
                continue
            if not os.path.exists(v) and not k.endswith("_out"):   # *_out folders are made on first write
                bad.append(f"path {k}: {v}")
        for k, v in self.get("brand", {}).items():
            if isinstance(v, str) and k.endswith(("_png", "_svg", "_mp4", "_mov")):
                f = self.asset(f"brand.{k}")
                if not os.path.exists(f):
                    bad.append(f"brand.{k}: {f}")
        return bad


def load(name=None):
    """Load a profile by name, folder or profile.json path. None -> $VIDEO_PROFILE -> local.json default."""
    name = name or os.environ.get("VIDEO_PROFILE") or _local().get("default_profile")
    if not name:
        raise ProfileError("no profile given: pass --profile <name>, set VIDEO_PROFILE, or run "
                           "`python3 engine/vprofile.py default <name>`. Profiles: " + ", ".join(available()))
    if os.path.isfile(name):
        path = name
    elif os.path.isdir(name) and (os.path.isfile(os.path.join(name, "profile.json")) or os.sep in name
                                  or not os.path.isfile(os.path.join(PROFILES, name, "profile.json"))):
        path = os.path.join(name, "profile.json")
    else:   # a bare name: profiles/<name>, even when the current folder happens to hold a folder of that name
        path = os.path.join(PROFILES, name, "profile.json")
    if not os.path.isfile(path):
        raise ProfileError(f"profile {name!r} not found (looked for {path}). Profiles: " + ", ".join(available()))
    with open(path) as f:
        data = json.load(f)
    return Profile(data, os.path.dirname(os.path.abspath(path)))


# ---- CLI ---------------------------------------------------------------------------------------------------
def _new(a):
    folder = os.path.join(PROFILES, a.name)
    if os.path.exists(folder):
        sys.exit(f"profile {a.name} already exists: {folder}")
    with open(os.path.join(PROFILES, "_template", "profile.json")) as f:
        data = json.load(f)
    data["name"] = a.name
    data["display_name"] = a.display or a.name
    if a.primary: data["brand"]["colors"]["primary"] = a.primary
    if a.accent: data["brand"]["colors"]["accent"] = a.accent
    os.makedirs(os.path.join(folder, "assets"), exist_ok=True)
    for role, src in (("head", a.head_font), ("body", a.body_font)):
        if src:
            dst = os.path.join("assets", os.path.basename(src))
            import shutil; shutil.copy2(src, os.path.join(folder, dst))
            data["brand"]["fonts"][role] = dst
    if a.logo:
        import shutil; dst = os.path.join("assets", os.path.basename(a.logo))
        shutil.copy2(a.logo, os.path.join(folder, dst))
        data["brand"]["logo_svg" if a.logo.lower().endswith(".svg") else "logo_png"] = dst
    if a.root:
        data["paths"]["root"] = a.root
    with open(os.path.join(folder, "profile.json"), "w") as f:
        json.dump(data, f, indent=2); f.write("\n")
    print(f"created {folder}/profile.json")
    if a.sample:
        _sample(load(folder), os.path.join(folder, "sample_card.png"))


def _sample(P, out):
    """Render one lower-third style card from the profile so a new profile can be checked by eye."""
    from PIL import Image, ImageDraw, ImageFont
    W, H = 1920, 1080
    im = Image.new("RGB", (W, H), (40, 40, 40)); d = ImageDraw.Draw(im)
    d.rectangle([90, 760, 1100, 960], fill=P.rgb("primary"))
    d.rectangle([90, 760, 104, 960], fill=P.rgb("accent"))
    d.text((140, 780), P.get("display_name", P.name).upper(), font=ImageFont.truetype(P.font("head"), 96),
           fill=P.rgb("text") if "text" in P.get("brand.colors") else (255, 255, 255))
    d.text((140, 890), "SAMPLE LOWER THIRD · 0123456789", font=ImageFont.truetype(P.font("body"), 44),
           fill=P.rgb("accent"))
    im.save(out); print(f"sample card: {out}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="list, show, check and create profiles")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    s = sub.add_parser("show"); s.add_argument("name", nargs="?"); s.add_argument("--check", action="store_true")
    n = sub.add_parser("new"); n.add_argument("name"); n.add_argument("--display"); n.add_argument("--primary")
    n.add_argument("--accent"); n.add_argument("--head-font"); n.add_argument("--body-font"); n.add_argument("--logo")
    n.add_argument("--root"); n.add_argument("--sample", action="store_true")
    d = sub.add_parser("default"); d.add_argument("name")
    c = sub.add_parser("sample"); c.add_argument("name"); c.add_argument("out")
    a = ap.parse_args(argv)
    if a.cmd == "list":
        dflt = os.environ.get("VIDEO_PROFILE") or _local().get("default_profile")
        for p in available():
            print(("* " if p == dflt else "  ") + p)
    elif a.cmd == "show":
        P = load(a.name)
        print(f"{P.name}  ({P.folder})")
        for role in P.get("brand.colors"): print(f"  color {role:10s} {P.color(role)}")
        for role in P.get("brand.fonts"): print(f"  font  {role:10s} {P.font(role)}")
        opt = P.optional_paths()
        for k in sorted(P._paths):
            print(f"  path  {k:14s} {P.path(k)}" + ("   (optional: machine-only)" if k in opt else ""))
        if a.check:
            bad, miss_opt = P.check(), P.check_optional()
            if miss_opt:
                print("optional, missing here (fine on a machine that doesn't use them):\n  " + "\n  ".join(miss_opt))
            print("CHECK: OK" if not bad else "CHECK: missing\n  " + "\n  ".join(bad))
            sys.exit(1 if bad else 0)
    elif a.cmd == "new":
        _new(a)
    elif a.cmd == "default":
        load(a.name)
        data = _local(); data["default_profile"] = a.name
        with open(LOCAL, "w") as f:
            json.dump(data, f, indent=2); f.write("\n")
        print(f"default profile on this machine: {a.name} ({LOCAL})")
    elif a.cmd == "sample":
        _sample(load(a.name), a.out)


if __name__ == "__main__":
    main()
