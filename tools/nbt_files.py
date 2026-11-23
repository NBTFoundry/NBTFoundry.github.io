# SPDX-License-Identifier: MPL-2.0
"""Reads and verifies NBT Manager's signed files: an application package (.nbt,
NBTMGR1) against the apps key, a manager release (.nbtr, NBTRLS1-3) against the
manager key. The layouts are NBTFoundry/manager's tools/package.py and
tools/package_release.py; the car's checks (nbt-verify) remain the authority."""

import hashlib
import re
import struct
import subprocess
import tempfile
from pathlib import Path

SIGNATURE = 384
PACKAGE_MANIFEST_MAX = 2048
RELEASE_MANIFEST_MAX = 4096
PAYLOAD_MAX = 64 * 1024 * 1024
APP = re.compile(r"[a-z0-9_-]{1,48}\Z")
TOKEN = re.compile(r"[a-z0-9_.-]{1,48}\Z")
VERSION = re.compile(r"[A-Za-z0-9_.-]{1,48}\Z")
SEQUENCE = re.compile(r"[1-9][0-9]{0,19}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
BRIDGE = re.compile(r"[0-9]{1,3}\.[0-9]{1,3}\Z")
PRINTABLE = re.compile(r"[ -~]*\Z")
PACKAGE_ORDER = ("app", "package", "version", "sequence", "platform", "compat", "size", "sha256")
COMPONENTS_V1 = ("launcher", "gui", "worker", "plugin_lib", "plugin_manifest", "plugin_xml",
                 "plugin_text", "plugin_images")
COMPONENT = re.compile(r"([a-z][a-z0-9_]{0,23})_size=")


class Invalid(Exception):
    """The file is not a well-formed, correctly signed package or release."""


def _require(condition, reason):
    if not condition:
        raise Invalid(reason)


def _verify_signature(signed, signature, key):
    """RSA PKCS#1 v1.5 over SHA-256 (openssl dgst -sha256 -sign), as the manager checks it."""
    with tempfile.TemporaryDirectory() as work:
        data, sig = Path(work, "signed"), Path(work, "signature")
        data.write_bytes(signed)
        sig.write_bytes(signature)
        result = subprocess.run(["openssl", "dgst", "-sha256", "-verify", str(key), "-signature", str(sig), str(data)],
                                capture_output=True, check=False)
    _require(result.returncode == 0, "bad signature")


def _sha256(stream, size):
    digest, left = hashlib.sha256(), size
    while left:
        block = stream.read(min(left, 1 << 20))
        _require(block, "truncated")
        digest.update(block)
        left -= len(block)
    return digest.hexdigest()


def _manifest(raw):
    _require(raw.endswith(b"\n"), "manifest")
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError as error:
        raise Invalid("manifest") from error
    lines = text[:-1].split("\n")
    _require(all(PRINTABLE.fullmatch(line) for line in lines), "manifest")
    return lines


def read_package(path, apps_key):
    """The manifest of a verified application package, as the catalog shows it."""
    path = Path(path)
    size = path.stat().st_size
    with path.open("rb") as stream:
        header = stream.read(24)
        _require(len(header) == 24, "truncated")
        magic, manifest_size, signature_size, payload_size = struct.unpack(">8sIIQ", header)
        _require(magic == b"NBTMGR1\n" and 0 < manifest_size <= PACKAGE_MANIFEST_MAX
                 and signature_size == SIGNATURE and 52 <= payload_size <= PAYLOAD_MAX
                 and size == 24 + manifest_size + SIGNATURE + payload_size, "header")
        raw = stream.read(manifest_size)
        signature = stream.read(SIGNATURE)
        _require(len(raw) == manifest_size and len(signature) == SIGNATURE, "truncated")
        _verify_signature(header + raw, signature, apps_key)
        lines = _manifest(raw)
        _require(len(lines) >= len(PACKAGE_ORDER), "manifest")
        values = {}
        for name, line in zip(PACKAGE_ORDER, lines):
            _require(line.startswith(name + "="), "manifest")
            values[name] = line[len(name) + 1:]
        _require(APP.fullmatch(values["app"]) and values["app"] != "manager"
                 and VERSION.fullmatch(values["version"]) and SEQUENCE.fullmatch(values["sequence"])
                 and int(values["sequence"]) < 2**64 and values["platform"] == "qnx6.5-armv7le"
                 and TOKEN.fullmatch(values["compat"]) and values["size"] == str(payload_size)
                 and HEX64.fullmatch(values["sha256"]), "manifest")
        _require(_sha256(stream, payload_size) == values["sha256"], "payload digest")
    rest = lines[len(PACKAGE_ORDER):]
    bridge = next((line[7:] for line in rest if line.startswith("bridge=")), None)
    properties = []
    for line in rest:
        if line.startswith("property="):
            label, _, value = line[9:].partition("|")
            if label and value:
                properties.append({"label": label, "value": value})
    return {
        "app": values["app"],
        "version": values["version"],
        "sequence": values["sequence"],
        "compat": values["compat"],
        "bridge": bridge if bridge and BRIDGE.fullmatch(bridge) else None,
        "properties": properties[:8],
        "text": [line[5:] for line in rest if line.startswith("text=")][:20],
    }


def read_release(path, manager_key):
    """The manifest of a verified manager release."""
    path = Path(path)
    size = path.stat().st_size
    with path.open("rb") as stream:
        header = stream.read(16)
        _require(len(header) == 16, "truncated")
        magic, manifest_size, signature_size = struct.unpack(">8sII", header)
        formats = {b"NBTRLS1\n": 1, b"NBTRLS2\n": 2, b"NBTRLS3\n": 3}
        _require(magic in formats and 0 < manifest_size <= RELEASE_MANIFEST_MAX
                 and signature_size == SIGNATURE, "header")
        release_format = formats[magic]
        raw = stream.read(manifest_size)
        signature = stream.read(SIGNATURE)
        _require(len(raw) == manifest_size and len(signature) == SIGNATURE, "truncated")
        _verify_signature(header + raw, signature, manager_key)
        lines = _manifest(raw)

        def field(name):
            _require(lines and lines[0].startswith(name + "="), "manifest")
            return lines.pop(0)[len(name) + 1:]

        version, sequence, platform, compat = (field(n) for n in ("version", "sequence", "platform", "compat"))
        _require(VERSION.fullmatch(version) and SEQUENCE.fullmatch(sequence) and int(sequence) < 2**64
                 and platform == "qnx6.5-armv7le" and TOKEN.fullmatch(compat), "manifest")
        while lines and lines[0].startswith("bridge="):
            lines.pop(0)
        names = list(COMPONENTS_V1) + (["capture_lib"] if release_format == 2 else [])
        components = []
        index = 0
        while index < len(names) or (release_format == 3 and lines):
            if index == len(names):
                match = COMPONENT.match(lines[0])
                _require(match and match.group(1) not in names and len(names) < len(COMPONENTS_V1) + 8, "manifest")
                names.append(match.group(1))
            name = names[index]
            length, digest = field(f"{name}_size"), field(f"{name}_sha256")
            _require(re.fullmatch(r"0|[1-9][0-9]{0,8}", length) and int(length) <= PAYLOAD_MAX
                     and HEX64.fullmatch(digest), "manifest")
            components.append((int(length), digest))
            index += 1
        _require(not lines and size == 16 + manifest_size + SIGNATURE + sum(c[0] for c in components), "manifest")
        for length, digest in components:
            _require(_sha256(stream, length) == digest, "component digest")
    return {"app": "manager", "version": version, "sequence": sequence, "compat": compat, "format": release_format}
