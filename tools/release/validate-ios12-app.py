#!/usr/bin/env python3
"""Read-only deployment/dependency checks for an archived iOS device app.

This inspects the produced Mach-O files, not just Xcode build settings. It does
not establish that every imported symbol exists on the device or test signing.
"""

import argparse
import mmap
import plistlib
import struct
import sys
from dataclasses import dataclass
from pathlib import Path


THIN = {
    b"\xce\xfa\xed\xfe": ("<", 28), b"\xcf\xfa\xed\xfe": ("<", 32),
    b"\xfe\xed\xfa\xce": (">", 28), b"\xfe\xed\xfa\xcf": (">", 32),
}
FAT = {
    b"\xca\xfe\xba\xbe": (">", False), b"\xbe\xba\xfe\xca": ("<", False),
    b"\xca\xfe\xba\xbf": (">", True), b"\xbf\xba\xfe\xca": ("<", True),
}
ARM64 = 0x0100000C
WEAK_DYLIB = 0x80000018
DYLIB_COMMANDS = {0xC, WEAK_DYLIB, 0x8000001F, 0x80000023, 0x20}
UNAVAILABLE_ON_IOS12 = {
    "CryptoKit": (13, 0, 0),
    "QuickLookThumbnailing": (13, 0, 0),
    "UniformTypeIdentifiers": (14, 0, 0),
    "libswift_Concurrency.dylib": (13, 0, 0),
}
# PhotosUI itself exists on iOS 8+. Its newer PHPicker APIs need availability
# guards, but a dependency on the framework does not imply iOS 14 is required.


def version(value):
    pieces = tuple(int(part) for part in value.split("."))
    if not 1 <= len(pieces) <= 3 or any(part < 0 for part in pieces):
        raise ValueError("expected an OS version such as 12.1.1")
    return pieces + (0,) * (3 - len(pieces))


def unpack_version(value):
    return value >> 16, (value >> 8) & 0xFF, value & 0xFF


def format_version(value):
    return ".".join(str(part) for part in value)


@dataclass
class MachSlice:
    cpu: int
    subtype: int
    minimum: tuple | None
    platform: int | None
    dependencies: list
    rpaths: list


def macho_slices(data, start=0, size=None):
    """Parse thin/fat, 32/64-bit and either-endian Mach-O load commands."""
    size = len(data) - start if size is None else size
    end = start + size
    if size < 4 or start < 0 or end > len(data):
        raise ValueError("truncated Mach-O slice")
    magic = data[start:start + 4]
    if magic in FAT:
        endian, wide = FAT[magic]
        if size < 8:
            raise ValueError("truncated universal header")
        count = struct.unpack_from(endian + "I", data, start + 4)[0]
        entry_size = 32 if wide else 20
        if count == 0 or 8 + count * entry_size > size:
            raise ValueError("invalid universal architecture table")
        slices = []
        for i in range(count):
            entry = start + 8 + i * entry_size
            offset, length = struct.unpack_from(endian + ("QQ" if wide else "II"), data, entry + 8)
            if offset < 8 + count * entry_size or offset + length > size:
                raise ValueError("universal slice is outside its container")
            if data[start + offset:start + offset + 4] not in THIN:
                raise ValueError("universal architecture is not a thin Mach-O")
            slices.extend(macho_slices(data, start + offset, length))
        return slices
    if magic not in THIN:
        raise ValueError("not a Mach-O file")
    endian, header_size = THIN[magic]
    if size < header_size:
        raise ValueError("truncated Mach-O header")
    cpu, subtype, _, count, command_bytes = struct.unpack_from(endian + "IIIII", data, start + 4)
    command_end = start + header_size + command_bytes
    if command_end > end or count > command_bytes // 8:
        raise ValueError("invalid Mach-O load-command table")
    minimum = platform = None
    dependencies, rpaths = [], []
    cursor = start + header_size
    for _ in range(count):
        if cursor + 8 > command_end:
            raise ValueError("truncated load command")
        command, length = struct.unpack_from(endian + "II", data, cursor)
        if length < 8 or cursor + length > command_end:
            raise ValueError("invalid load-command size")
        if command == 0x32:  # LC_BUILD_VERSION
            if length < 24:
                raise ValueError("truncated LC_BUILD_VERSION")
            platform, encoded = struct.unpack_from(endian + "II", data, cursor + 8)
            minimum = unpack_version(encoded)
        elif command in {0x24, 0x25, 0x2F, 0x30}:  # legacy version_min commands
            if length < 16:
                raise ValueError("truncated deployment command")
            platform = {0x24: 1, 0x25: 2, 0x2F: 3, 0x30: 4}[command]
            minimum = unpack_version(struct.unpack_from(endian + "I", data, cursor + 8)[0])
        elif command in DYLIB_COMMANDS or command == 0x8000001C:
            minimum_size = 24 if command in DYLIB_COMMANDS else 12
            if length < minimum_size:
                raise ValueError("truncated library/path command")
            offset = struct.unpack_from(endian + "I", data, cursor + 8)[0]
            if not minimum_size <= offset < length:
                raise ValueError("invalid library/path string offset")
            raw = bytes(data[cursor + offset:cursor + length])
            if b"\0" not in raw:
                raise ValueError("unterminated library/path string")
            name = raw.split(b"\0", 1)[0].decode("utf-8")
            if command == 0x8000001C:
                rpaths.append(name)
            else:
                dependencies.append((name, command == WEAK_DYLIB))
        cursor += length
    if cursor != command_end:
        raise ValueError("load-command count does not match its byte size")
    return [MachSlice(cpu, subtype, minimum, platform, dependencies, rpaths)]


def read_macho(path):
    with path.open("rb") as file:
        if file.read(4) not in THIN | FAT:
            return None
        file.seek(0)
        with mmap.mmap(file.fileno(), 0, access=mmap.ACCESS_READ) as data:
            return macho_slices(data)


def audit_app(app, target):
    app = app.resolve()
    errors, binaries, executables, bundle_binaries = [], {}, [], []

    def label(path):
        return str(path.relative_to(app))

    def inside(path):
        return path == app or app in path.parents

    bundles = [app] + sorted(app.rglob("*.appex")) + sorted(app.rglob("*.framework"))
    for bundle in bundles:
        try:
            with (bundle / "Info.plist").open("rb") as file:
                info = plistlib.load(file)
            if info.get("MinimumOSVersion") and version(info["MinimumOSVersion"]) > target:
                errors.append(f"{label(bundle / 'Info.plist')}: MinimumOSVersion {info['MinimumOSVersion']} exceeds {format_version(target)}")
            executable = info.get("CFBundleExecutable")
            if not executable or Path(executable).name != executable:
                raise ValueError("missing or invalid CFBundleExecutable")
            path = (bundle / executable).resolve()
            if not inside(path) or not path.is_file():
                raise ValueError(f"missing bundle executable {executable}")
            bundle_binaries.append(path)
            if bundle == app or bundle.suffix == ".appex":
                executables.append(path)
        except (OSError, ValueError, plistlib.InvalidFileException) as error:
            errors.append(f"{label(bundle)}: {error}")

    for required in (app / "PlugIns/Reynard Helper.appex", app / "PlugIns/OpenIn.appex",
                     app / "Frameworks/GeckoView.framework/XUL"):
        if not required.exists():
            errors.append(f"missing required Gecko/app component: {label(required)}")

    for path in sorted(app.rglob("*")):
        if not path.is_file():
            continue
        resolved = path.resolve()
        if not inside(resolved):
            errors.append(f"{label(path)}: symlink escapes the application bundle")
            continue
        if resolved in binaries:
            continue
        try:
            slices = read_macho(resolved)
            if slices is None:
                if path.suffix == ".dylib":
                    errors.append(f"{label(path)}: dynamic library is not valid Mach-O code")
                continue
            binaries[resolved] = slices
            compatible = [s for s in slices if s.cpu == ARM64 and s.subtype & 0xFFFFFF != 2]
            if not compatible:
                errors.append(f"{label(path)}: missing a regular arm64 device slice")
            for item in slices:
                if item.minimum is None or item.platform != 2:
                    errors.append(f"{label(path)}: missing iOS device deployment metadata")
                elif item.minimum > target:
                    errors.append(f"{label(path)}: binary requires iOS {format_version(item.minimum)}")
                for name, weak in item.dependencies:
                    if not weak and target < (12, 2, 0) and name.startswith("/usr/lib/swift/libswift"):
                        errors.append(f"{label(path)}: system Swift runtime is unavailable before iOS 12.2: {name}")
                    since = UNAVAILABLE_ON_IOS12.get(Path(name).name)
                    if not weak and since and since > target:
                        errors.append(f"{label(path)}: strong dependency unavailable on iOS 12: {name}")
        except (OSError, ValueError, struct.error, UnicodeDecodeError) as error:
            errors.append(f"{label(path)}: {error}")

    for executable in bundle_binaries:
        if executable not in binaries:
            errors.append(f"{label(executable)}: bundle executable is not a valid Mach-O")
    xul = (app / "Frameworks/GeckoView.framework/XUL").resolve()
    if xul not in binaries:
        errors.append("Frameworks/GeckoView.framework/XUL: missing valid Gecko engine Mach-O")

    def expand(name, loader, executable):
        for prefix, directory in (("@loader_path", loader.parent), ("@executable_path", executable.parent)):
            if name == prefix or name.startswith(prefix + "/"):
                return (directory / name[len(prefix):].lstrip("/")).resolve()
        return Path(name).resolve() if name.startswith("/") else None

    # dyld resolves @rpath against the chain of loaders for each executable.
    # Walk every embedded image too: XUL can be opened dynamically rather than
    # appearing directly in the host executable's library commands.
    visited = set()

    def walk(loader, executable, inherited, active):
        if loader in active:
            return
        for item in binaries.get(loader, []):
            if item.cpu != ARM64 or item.subtype & 0xFFFFFF == 2:
                continue
            own = tuple(p for name in item.rpaths if (p := expand(name, loader, executable)) is not None)
            paths = own + inherited
            state = (loader, executable, paths)
            if state in visited:
                continue
            visited.add(state)
            for name, weak in item.dependencies:
                if name.startswith(("/System/Library/", "/usr/lib/")):
                    continue
                if name.startswith("@rpath/"):
                    candidates = [directory / name[7:] for directory in paths]
                else:
                    path = expand(name, loader, executable)
                    candidates = [path] if path else []
                dependency = next((p.resolve() for p in candidates if p.is_file()), None)
                if dependency is None:
                    if not weak:
                        errors.append(f"{label(loader)}: missing embedded dependency {name} (launching {label(executable)})")
                elif not inside(dependency) or dependency not in binaries:
                    errors.append(f"{label(loader)}: dependency is not bundled Mach-O code: {name}")
                else:
                    walk(dependency, executable, paths, active | {loader})

    if executables:
        for executable in executables:
            walk(executable, executable, (), set())
        host = executables[0]
        host_paths = tuple(p for s in binaries.get(host, []) for name in s.rpaths
                           if (p := expand(name, host, host)) is not None)
        for binary in binaries:
            if not any(state[0] == binary for state in visited):
                walk(binary, host, host_paths, set())
    if not binaries:
        errors.append("application contains no Mach-O binaries")
    return sorted(set(errors)), len(binaries)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("app", type=Path, help="path to archived .app")
    parser.add_argument("--os-version", default="12.1.1")
    args = parser.parse_args()
    if not args.app.is_dir() or args.app.suffix != ".app":
        parser.error("app must be an existing .app directory")
    try:
        target = version(args.os_version)
    except ValueError as error:
        parser.error(str(error))
    errors, count = audit_app(args.app, target)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"Validated {count} Mach-O files for iOS {format_version(target)}; deployment targets and bundled dependencies passed.")
    print("Device launch, imported-symbol availability and signing still require device verification.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
