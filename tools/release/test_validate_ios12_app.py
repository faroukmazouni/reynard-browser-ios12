"""Synthetic Mach-O fixtures; no Apple SDK or actual engine build required."""

import importlib.util
import plistlib
import struct
import sys
import tempfile
import unittest
from pathlib import Path


spec = importlib.util.spec_from_file_location("ios12_validator", Path(__file__).with_name("validate-ios12-app.py"))
validator = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = validator
sys.dont_write_bytecode = True
spec.loader.exec_module(validator)


def thin(minimum=(12, 0, 0), dependencies=(), rpaths=(), endian="<", wide=True, legacy=False, platform=2):
    def string_command(command, name, size):
        encoded = name.encode() + b"\0"
        length = (size + len(encoded) + 7) & ~7
        prefix = struct.pack(endian + "III", command, length, size)
        return prefix + bytes(size - len(prefix)) + encoded + bytes(length - size - len(encoded))

    encoded = minimum[0] << 16 | minimum[1] << 8 | minimum[2]
    commands = [struct.pack(endian + "IIII", 0x25, 16, encoded, 0)] if legacy else [struct.pack(endian + "IIIIII", 0x32, 24, platform, encoded, 0, 0)]
    commands += [string_command(0x8000001C, path, 12) for path in rpaths]
    commands += [string_command(validator.WEAK_DYLIB if weak else 0xC, name, 24) for name, weak in dependencies]
    content = b"".join(commands)
    values = [0xFEEDFACF if wide else 0xFEEDFACE, validator.ARM64, 0, 6, len(commands), len(content), 0]
    if wide:
        values.append(0)
    return struct.pack(endian + "I" * len(values), *values) + content


def universal(blobs, wide=False, endian=">"):
    entry_size = 32 if wide else 20
    offset = 8 + entry_size * len(blobs)
    table, content = [], []
    for blob in blobs:
        if wide:
            table.append(struct.pack(endian + "IIQQII", validator.ARM64, 0, offset, len(blob), 0, 0))
        else:
            table.append(struct.pack(endian + "IIIII", validator.ARM64, 0, offset, len(blob), 0))
        content.append(blob)
        offset += len(blob)
    return struct.pack(endian + "II", 0xCAFEBABF if wide else 0xCAFEBABE, len(blobs)) + b"".join(table + content)


class ValidatorTests(unittest.TestCase):
    def bundle(self, root):
        app = root / "Reynard.app"

        def executable(bundle, name, dependencies=(), rpaths=()):
            bundle.mkdir(parents=True, exist_ok=True)
            with (bundle / "Info.plist").open("wb") as file:
                plistlib.dump({"CFBundleExecutable": name, "MinimumOSVersion": "12.0"}, file)
            (bundle / name).write_bytes(thin(dependencies=dependencies, rpaths=rpaths))

        gecko = "@rpath/GeckoView.framework/GeckoView"
        executable(app, "Reynard", [(gecko, False)], ["@executable_path/Frameworks"])
        executable(app / "PlugIns/Reynard Helper.appex", "Reynard Helper", [(gecko, False)], ["@executable_path/../../Frameworks"])
        executable(app / "PlugIns/OpenIn.appex", "OpenIn")
        framework = app / "Frameworks/GeckoView.framework"
        executable(framework, "GeckoView", [("@loader_path/XUL", False)], ["@loader_path/.."])
        (framework / "XUL").write_bytes(thin(dependencies=[("@rpath/libmozglue.dylib", False)]))
        (app / "Frameworks/libmozglue.dylib").write_bytes(thin())
        return app

    def test_thin_versions_endianness_and_legacy(self):
        for endian in ("<", ">"):
            for wide in (False, True):
                for legacy in (False, True):
                    with self.subTest(endian=endian, wide=wide, legacy=legacy):
                        parsed = validator.macho_slices(thin(endian=endian, wide=wide, legacy=legacy))[0]
                        self.assertEqual(parsed.minimum, (12, 0, 0))
                        self.assertEqual(parsed.platform, 2)

    def test_universal_32_and_64(self):
        for endian in ("<", ">"):
            for wide in (False, True):
                parsed = validator.macho_slices(universal([thin(), thin((13, 0, 0))], wide, endian))
                self.assertEqual([s.minimum for s in parsed], [(12, 0, 0), (13, 0, 0)])

    def test_corrupt_macho_rejected(self):
        for blob in (thin()[:24], universal([thin()])[:-1], thin()[:32] + bytes(24)):
            with self.subTest(length=len(blob)), self.assertRaises(ValueError):
                validator.macho_slices(blob)

    def test_complete_bundle_resolves_host_and_extension_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            errors, count = validator.audit_app(self.bundle(Path(directory)), (12, 1, 1))
            self.assertEqual(errors, [])
            self.assertEqual(count, 6)

    def test_missing_embedded_library_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            app = self.bundle(Path(directory))
            (app / "Frameworks/libmozglue.dylib").unlink()
            errors, _ = validator.audit_app(app, (12, 1, 1))
            self.assertTrue(any("missing embedded dependency @rpath/libmozglue" in error for error in errors))

    def test_newer_slice_and_strong_new_framework_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            app = self.bundle(Path(directory))
            (app / "Frameworks/libmozglue.dylib").write_bytes(universal([
                thin(), thin((13, 0, 0), dependencies=[("/System/Library/Frameworks/CryptoKit.framework/CryptoKit", False)])
            ]))
            errors, _ = validator.audit_app(app, (12, 1, 1))
            self.assertTrue(any("binary requires iOS 13" in error for error in errors))
            self.assertTrue(any("strong dependency unavailable" in error for error in errors))

    def test_weak_new_framework_and_photosui_allowed(self):
        with tempfile.TemporaryDirectory() as directory:
            app = self.bundle(Path(directory))
            (app / "Frameworks/libmozglue.dylib").write_bytes(thin(dependencies=[
                ("/System/Library/Frameworks/UniformTypeIdentifiers.framework/UniformTypeIdentifiers", True),
                ("/System/Library/Frameworks/PhotosUI.framework/PhotosUI", False),
            ]))
            self.assertEqual(validator.audit_app(app, (12, 1, 1))[0], [])

    def test_missing_helper_and_wrong_platform_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            app = self.bundle(Path(directory))
            (app / "PlugIns/Reynard Helper.appex/Reynard Helper").unlink()
            (app / "Frameworks/libmozglue.dylib").write_bytes(thin(platform=7))
            errors, _ = validator.audit_app(app, (12, 1, 1))
            self.assertTrue(any("missing bundle executable" in error for error in errors))
            self.assertTrue(any("missing iOS device deployment metadata" in error for error in errors))

    def test_system_swift_is_missing_on_ios_12_1(self):
        with tempfile.TemporaryDirectory() as directory:
            app = self.bundle(Path(directory))
            (app / "Frameworks/libmozglue.dylib").write_bytes(thin(dependencies=[("/usr/lib/swift/libswiftCore.dylib", False)]))
            errors, _ = validator.audit_app(app, (12, 1, 1))
            self.assertTrue(any("system Swift runtime is unavailable" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
