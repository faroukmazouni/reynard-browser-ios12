#!/usr/bin/env python3
"""Expand Xcode 16 synchronized folders into Xcode 15 project entries.

This is a one-time migration tool. The checked-in project is already expanded;
rerunning it is harmless. Files subsequently added to ordinary groups must be
added to the appropriate build phase through Xcode.

An exception toggles membership: it excludes a file from a target that owns
the folder, but includes a file in a target that does not own the folder.
That distinction is essential for the two Helper sources and Shared/Utils.m.
"""

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT / "browser/Reynard.xcodeproj/project.pbxproj"
SOURCE_EXTENSIONS = {".swift", ".m", ".mm", ".c", ".cc", ".cpp"}
RESOURCE_EXTENSIONS = {".xcassets", ".storyboard", ".xib", ".strings", ".stringsdict", ".xcstrings"}
FILE_TYPES = {
    ".swift": "sourcecode.swift", ".m": "sourcecode.c.objc",
    ".mm": "sourcecode.cpp.objcpp", ".c": "sourcecode.c.c",
    ".h": "sourcecode.c.h", ".a": "archive.ar",
    ".plist": "text.plist.xml", ".entitlements": "text.plist.entitlements",
    ".storyboard": "file.storyboard", ".xcassets": "folder.assetcatalog",
}


def identifier(kind, *parts):
    return hashlib.sha1((kind + ":" + ":".join(parts)).encode()).hexdigest()[:24].upper()


def quote(value):
    return json.dumps(value, ensure_ascii=False)


def members(folder):
    """Treat asset catalogs as packages, never as hundreds of loose images."""
    result = []
    for directory, folders, files in os.walk(folder):
        folders[:] = sorted(name for name in folders if not name.startswith("."))
        for name in list(folders):
            if Path(name).suffix == ".xcassets":
                result.append((Path(directory) / name).relative_to(folder).as_posix())
                folders.remove(name)
        result.extend((Path(directory) / name).relative_to(folder).as_posix()
                      for name in sorted(files) if not name.startswith("."))
    return sorted(result)


def main():
    text = PROJECT.read_text()
    project = json.loads(subprocess.check_output(
        ["plutil", "-convert", "json", "-o", "-", str(PROJECT)]))
    objects = project["objects"]
    roots = {key: value for key, value in objects.items()
             if value["isa"] == "PBXFileSystemSynchronizedRootGroup"}
    if not roots:
        print("Project already uses explicit Xcode 15-compatible file entries.")
        return

    new_references = []
    new_groups = []
    new_build_files = []
    phase_members = {}
    targets = {key: value for key, value in objects.items()
               if value["isa"] == "PBXNativeTarget"}

    for group_id, group in sorted(roots.items()):
        directory = ROOT / "browser" / group["path"]
        paths = members(directory)
        # Built by build-idevice.sh before Xcode starts; it must still be
        # registered in a clean source checkout where the archive is absent.
        if group["path"] == "Reynard" and "JIT/RPPairing/libidevice_ffi.a" not in paths:
            paths.append("JIT/RPPairing/libidevice_ffi.a")
            paths.sort()
        file_ids = {}
        for relative_path in paths:
            file_id = identifier("file", group["path"], relative_path)
            file_ids[relative_path] = file_id
            file_type = FILE_TYPES.get(Path(relative_path).suffix, "text")
            new_references.append(
                f'\t\t{file_id} /* {relative_path} */ = {{isa = PBXFileReference; '
                f'lastKnownFileType = {quote(file_type)}; path = {quote(relative_path)}; sourceTree = "<group>"; }};')

        new_groups.append(
            f'\t\t{group_id} /* {group["path"]} */ = {{\n'
            '\t\t\tisa = PBXGroup;\n\t\t\tchildren = (\n' +
            "".join(f'\t\t\t\t{file_ids[path]} /* {path} */,\n' for path in paths) +
            f'\t\t\t);\n\t\t\tpath = {quote(group["path"])};\n'
            '\t\t\tsourceTree = "<group>";\n\t\t};')

        exceptions = {objects[key]["target"]: set(objects[key].get("membershipExceptions", []))
                      for key in group.get("exceptions", [])}
        for target_id, target in targets.items():
            owns_folder = group_id in target.get("fileSystemSynchronizedGroups", [])
            toggles = exceptions.get(target_id, set())
            phases = {objects[key]["isa"]: key for key in target["buildPhases"]}
            for path in paths:
                if owns_folder == (path in toggles):
                    continue
                extension = Path(path).suffix
                if extension in SOURCE_EXTENSIONS:
                    phase_type = "PBXSourcesBuildPhase"
                elif extension in RESOURCE_EXTENSIONS:
                    phase_type = "PBXResourcesBuildPhase"
                elif extension == ".a":
                    phase_type = "PBXFrameworksBuildPhase"
                else:
                    continue
                phase_id = phases[phase_type]
                file_id = file_ids[path]
                build_id = identifier("build", target_id, group["path"], path)
                new_build_files.append(
                    f'\t\t{build_id} /* {path} in {target["name"]} */ = '
                    f'{{isa = PBXBuildFile; fileRef = {file_id} /* {path} */; }};')
                phase_members.setdefault(phase_id, []).append(
                    f'\t\t\t\t{build_id} /* {path} */,')

    for section in ("PBXFileSystemSynchronizedBuildFileExceptionSet", "PBXFileSystemSynchronizedRootGroup"):
        text, count = re.subn(
            rf'/\* Begin {section} section \*/.*?/\* End {section} section \*/\n\n?',
            "", text, flags=re.DOTALL)
        assert count == 1, section
    for section, lines in (("PBXBuildFile", new_build_files),
                           ("PBXFileReference", new_references), ("PBXGroup", new_groups)):
        end = f"/* End {section} section */"
        text = text.replace(end, "\n".join(lines) + "\n" + end, 1)
    for phase_id, lines in phase_members.items():
        pattern = rf'(\t\t{re.escape(phase_id)} /\*[^\n]+\*/ = \{{.*?\n\t\t\tfiles = \(\n)'
        text, count = re.subn(pattern, lambda match: match[1] + "\n".join(lines) + "\n",
                              text, count=1, flags=re.DOTALL)
        assert count == 1, phase_id
    text = re.sub(r'\n\t\t\tfileSystemSynchronizedGroups = \(.*?\n\t\t\t\);', "", text, flags=re.DOTALL)
    text = text.replace("objectVersion = 77;", "objectVersion = 60;")
    text = text.replace("\n\t\t\tpreferredProjectObjectVersion = 77;", "")
    text = text.replace("\n\t\t\tminimizedProjectReferenceProxies = 1;", "")
    text = text.replace('\n\t\t\tdevelopmentRegion = en;', '\n\t\t\tcompatibilityVersion = "Xcode 15.0";\n\t\t\tdevelopmentRegion = en;')
    PROJECT.write_text(text)
    subprocess.run(["plutil", "-lint", str(PROJECT)], check=True)
    print(f"Expanded {len(roots)} folders into {len(new_references)} file references and {len(new_build_files)} build entries.")


if __name__ == "__main__":
    main()
