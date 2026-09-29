"""Copy the Lookout addon into every installed WoW version's AddOns folder, or into the
one given with --game-dir (for example ".../World of Warcraft/_retail_")."""
import argparse
import glob
import os
import shutil
from pathlib import Path

from companion.chatlog import GAME_ROOTS

ADDON = Path(__file__).resolve().parent / "addon" / "Lookout"


def game_dirs():
    return sorted({Path(p).parent.parent for root in GAME_ROOTS
                   for p in glob.glob(os.path.join(root, "*", "Interface", "AddOns"))})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--game-dir", action="append", help="a game version folder; repeat for several")
    args = parser.parse_args(argv)
    targets = [Path(d) for d in args.game_dir] if args.game_dir else game_dirs()
    if not targets:
        print("No WoW install found. Pass --game-dir with your game folder, e.g. .../World of Warcraft/_retail_")
        return 1
    for game in targets:
        dest = game / "Interface" / "AddOns" / "Lookout"
        shutil.copytree(ADDON, dest, dirs_exist_ok=True)
        print(f"installed Lookout -> {dest}")
    print("In game: /reload, then /lo for commands. Start the companion with start-companion.cmd.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
