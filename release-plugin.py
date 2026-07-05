"""
Release the WP Pilot SEO plugin: bump version, rebuild the zip, deploy.

Usage:
  python release-plugin.py            # rebuild zip + deploy (no version bump)
  python release-plugin.py --bump     # bump patch version (1.0.0 -> 1.0.1), zip, deploy
  python release-plugin.py 1.2.0      # set exact version, zip, deploy

After deploy, every WordPress site running the plugin will see "Update available"
within ~6 hours (or instantly on the Plugins screen "Check for updates").
"""
import os
import re
import sys
import subprocess
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
PLUGIN_DIR = os.path.join(ROOT, "wp-pilot-seo")
MAIN_PHP = os.path.join(PLUGIN_DIR, "wp-pilot-seo.php")
SERVER_ZIP = os.path.join(ROOT, "wp-mcp", "plugin", "wp-pilot-seo.zip")


def read_version():
    txt = open(MAIN_PHP, encoding="utf-8").read()
    m = re.search(r"Version:\s*([0-9.]+)", txt)
    return m.group(1) if m else "1.0.0"


def set_version(new_v):
    txt = open(MAIN_PHP, encoding="utf-8").read()
    txt = re.sub(r"(\*\s*Version:\s*)[0-9.]+", r"\g<1>" + new_v, txt, count=1)
    txt = re.sub(r"(WPPSEO_VERSION',\s*')[0-9.]+", r"\g<1>" + new_v, txt, count=1)
    open(MAIN_PHP, "w", encoding="utf-8").write(txt)


def bump_patch(v):
    parts = v.split(".")
    parts[-1] = str(int(parts[-1]) + 1)
    return ".".join(parts)


def build_zip():
    os.makedirs(os.path.dirname(SERVER_ZIP), exist_ok=True)
    if os.path.exists(SERVER_ZIP):
        os.remove(SERVER_ZIP)
    with zipfile.ZipFile(SERVER_ZIP, "w", zipfile.ZIP_DEFLATED) as z:
        for dp, _, fs in os.walk(PLUGIN_DIR):
            for f in fs:
                full = os.path.join(dp, f)
                arc = os.path.relpath(full, ROOT).replace(os.sep, "/")
                z.write(full, arc)
    # also copy a download copy to repo root for the dashboard link
    import shutil
    shutil.copy(SERVER_ZIP, os.path.join(ROOT, "wp-pilot-seo.zip"))


def deploy():
    subprocess.run(
        ["railway", "up", "--service", "wp-mcp", "--detach"],
        cwd=os.path.join(ROOT, "wp-mcp"), check=False,
    )


def main():
    cur = read_version()
    if len(sys.argv) > 1:
        if sys.argv[1] == "--bump":
            new_v = bump_patch(cur)
            set_version(new_v)
            print(f"version {cur} -> {new_v}")
        elif re.match(r"^[0-9.]+$", sys.argv[1]):
            new_v = sys.argv[1]
            set_version(new_v)
            print(f"version {cur} -> {new_v}")
        else:
            print("unknown arg:", sys.argv[1]); return
    else:
        print(f"version unchanged ({cur})")

    build_zip()
    print("zip rebuilt ->", SERVER_ZIP)
    print("deploying to Railway...")
    deploy()
    print("done. Sites will see the update within ~6h (or force-check on Plugins screen).")


if __name__ == "__main__":
    main()
