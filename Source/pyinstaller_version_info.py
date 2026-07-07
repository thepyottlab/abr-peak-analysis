from pathlib import Path
from textwrap import dedent

from version import APP_VERSION


APP_NAME = "ABR Peak Analysis"
INTERNAL_NAME = "notebook"
ORIGINAL_FILENAME = "notebook.exe"
LANG_CODEPAGE = "040904B0"
TRANSLATION = "[1033, 1200]"


def windows_version_tuple(version):
    parts = version.split(".")
    if not 1 <= len(parts) <= 4:
        raise ValueError(f"APP_VERSION must have 1 to 4 numeric parts: {version!r}")

    numbers = []
    for part in parts:
        if not part.isdigit():
            raise ValueError(f"APP_VERSION contains a non-numeric part: {version!r}")
        value = int(part)
        if value > 65535:
            raise ValueError(f"APP_VERSION part exceeds Windows limit 65535: {version!r}")
        numbers.append(value)

    return tuple((numbers + [0, 0, 0, 0])[:4])


def write_version_info(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    file_version = windows_version_tuple(APP_VERSION)
    string_version = ".".join(str(part) for part in file_version)

    path.write_text(
        dedent(
            f"""\
            # UTF-8
            VSVersionInfo(
              ffi=FixedFileInfo(
                filevers={file_version!r},
                prodvers={file_version!r},
                mask=0x3f,
                flags=0x0,
                OS=0x40004,
                fileType=0x1,
                subtype=0x0,
                date=(0, 0)
              ),
              kids=[
                StringFileInfo([
                  StringTable(
                    {LANG_CODEPAGE!r},
                    [
                      StringStruct('FileDescription', {APP_NAME!r}),
                      StringStruct('FileVersion', {string_version!r}),
                      StringStruct('InternalName', {INTERNAL_NAME!r}),
                      StringStruct('OriginalFilename', {ORIGINAL_FILENAME!r}),
                      StringStruct('ProductName', {APP_NAME!r}),
                      StringStruct('ProductVersion', {string_version!r})
                    ])
                ]),
                VarFileInfo([VarStruct('Translation', {TRANSLATION})])
              ]
            )
            """
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    import sys

    output = sys.argv[1] if len(sys.argv) > 1 else "build/version_info.txt"
    write_version_info(output)
