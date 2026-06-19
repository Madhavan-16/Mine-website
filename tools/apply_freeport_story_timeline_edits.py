"""Publish freeport-story-timeline.png from the Cursor workspace master (no automated edits)."""



from __future__ import annotations



from pathlib import Path



from PIL import Image



_CANONICAL = Path(

    r"C:\Users\2000137443\.cursor\projects\c-Users-2000137443-Desktop-MiNe\assets"

    r"\c__Users_2000137443_AppData_Roaming_Cursor_User_workspaceStorage_0857666d882847fddcad502a2a764c0c_images_file_00000000bfe87208af13dcf8f2a0f82c-2491ca63-87fe-4b45-8655-1261a3d2452a.png"

)





def main() -> None:

    root = Path(__file__).resolve().parents[1]

    if not _CANONICAL.is_file():

        raise SystemExit(f"Missing canonical timeline source: {_CANONICAL}")



    im = Image.open(_CANONICAL).convert("RGB")

    dests = [

        root / "static" / "img" / "freeport-story-timeline.png",

        root / "static_site" / "img" / "freeport-story-timeline.png",

    ]

    for d in dests:

        d.parent.mkdir(parents=True, exist_ok=True)

        im.save(d, "PNG", optimize=True)

    print("Wrote", dests, "size", im.size)





if __name__ == "__main__":

    main()

