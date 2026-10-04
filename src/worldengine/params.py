"""Parameter files: every number of the engine lives in YAML, checked on loading (design, Layer 1).

Each file has a schema in data/schemas: a written list of the allowed keys, types and ranges.
A file that breaks its schema stops the engine before anything runs, and the message names
the file, the key and the reason.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from types import MappingProxyType

import yaml


class ParameterError(Exception):
    """A parameter file is missing, malformed, or breaks its schema."""


_NUMBER_AS_TEXT = re.compile(r"^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$")

DEFAULT_DATA_DIR = Path(__file__).resolve().parents[2] / "data"

FILES = ("planet", "models", "profiles", "stages", "fields", "tables", "seeds", "interventions", "explanations")
OPTIONAL = {"interventions": [], "explanations": {}}


def _check(value, schema, where, problems):
    t = schema.get("type", "any")
    if value is None and schema.get("nullable"):
        return
    if t == "any":
        return
    if t in ("number", "integer"):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            if isinstance(value, str) and _NUMBER_AS_TEXT.match(value.strip()):
                problems.append(f"{where}: {value!r} is text, not a number. YAML reads a number such as 1e-5 as text; "
                                f"write it with a decimal point, as 1.0e-5")
            else:
                problems.append(f"{where}: expected a number, found {type(value).__name__} {value!r}")
            return
        if t == "integer" and not isinstance(value, int):
            problems.append(f"{where}: expected a whole number, found {value!r}")
            return
        if value != value:
            problems.append(f"{where}: is not a number (NaN)")
            return
        for key, test, word in (("min", lambda v, b: v >= b, "at least"), ("max", lambda v, b: v <= b, "at most"),
                                ("above", lambda v, b: v > b, "above"), ("below", lambda v, b: v < b, "below")):
            if key in schema and not test(value, schema[key]):
                problems.append(f"{where}: {value!r} must be {word} {schema[key]!r}")
    elif t == "string":
        if not isinstance(value, str):
            problems.append(f"{where}: expected text, found {type(value).__name__} {value!r}")
        elif "choices" in schema and value not in schema["choices"]:
            problems.append(f"{where}: {value!r} is not one of {', '.join(map(str, schema['choices']))}")
    elif t == "boolean":
        if not isinstance(value, bool):
            problems.append(f"{where}: expected true or false, found {value!r}")
    elif t == "list":
        if not isinstance(value, list):
            problems.append(f"{where}: expected a list, found {type(value).__name__}")
            return
        if "length" in schema and len(value) != schema["length"]:
            problems.append(f"{where}: expected {schema['length']} entries, found {len(value)}")
        for k, item in enumerate(value):
            _check(item, schema.get("items", {}), f"{where}[{k}]", problems)
    elif t == "map":
        if not isinstance(value, dict):
            problems.append(f"{where}: expected a map of keys, found {type(value).__name__}")
            return
        keys = schema.get("keys", {})
        for k in schema.get("required", []):
            if k not in value:
                problems.append(f"{where}: the key {k!r} is missing")
        for k, v in value.items():
            if not isinstance(k, str):
                problems.append(f"{where}: the key {k!r} must be text")
            elif k in keys:
                _check(v, keys[k], f"{where}.{k}", problems)
            elif "values" in schema:
                _check(v, schema["values"], f"{where}.{k}", problems)
            else:
                problems.append(f"{where}: the key {k!r} is not allowed here (allowed: {', '.join(sorted(keys)) or 'none'})")
    elif t == "one_of":
        errs = []
        for alt in schema["options"]:
            p = []
            _check(value, alt, where, p)
            if not p:
                return
            errs.append(p[0])
        problems.append(f"{where}: fits none of the allowed forms ({' | '.join(errs)})")
    else:
        problems.append(f"{where}: the schema names an unknown type {t!r}")


def validate(value, schema, name: str):
    problems: list[str] = []
    _check(value, schema, name, problems)
    if problems:
        raise ParameterError("; ".join(problems))


def _load_yaml(path: Path):
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ParameterError(f"{path.name}: the file is missing from {path.parent}") from None
    try:
        return text, yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise ParameterError(f"{path.name}: not valid YAML: {e}") from None


def freeze(value):
    """A read-only view of nested maps and lists, so that a process cannot change its parameters."""
    if isinstance(value, dict):
        return MappingProxyType({k: freeze(v) for k, v in value.items()})
    if isinstance(value, list):
        return tuple(freeze(v) for v in value)
    return value


def thaw(value):
    if isinstance(value, MappingProxyType) or isinstance(value, dict):
        return {k: thaw(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [thaw(v) for v in value]
    return value


def fingerprint(value) -> str:
    """A short code that changes if the value changes: SHA-256 of its canonical JSON form."""
    blob = json.dumps(thaw(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


class Parameters:
    """All parameter files of one data directory, checked against their schemas.

    `data` maps a file's stem to its parsed content; `text` keeps each file exactly as written,
    so that a world store can hold a full copy of what made it.
    """

    def __init__(self, data_dir, overrides: dict | None = None):
        self.data_dir = Path(data_dir)
        schema_dir = self.data_dir / "schemas"
        if not schema_dir.exists():                          # a data directory without schemas uses the engine's own
            schema_dir = DEFAULT_DATA_DIR / "schemas"
        self.data, self.text = {}, {}
        for stem in FILES:
            path = self.data_dir / f"{stem}.yaml"
            if not path.exists() and stem in OPTIONAL:
                self.text[stem], self.data[stem] = "", OPTIONAL[stem]
                continue
            self.text[stem], parsed = _load_yaml(path)
            if parsed is None and stem in OPTIONAL:
                parsed = OPTIONAL[stem]
            self.data[stem] = parsed
        for stem, value in (overrides or {}).items():
            if stem not in self.data:
                raise ParameterError(f"override names {stem!r}, which is not a parameter file")
            self.data[stem] = value
            self.text[stem] = yaml.safe_dump(value, sort_keys=False)
        # category lists and rule tables named by fields.yaml or models.yaml (biomes.yaml, soils.yaml, rocks.yaml)
        self.extra_files = {}
        for extra in sorted(p.stem for p in self.data_dir.glob("*.yaml") if p.stem not in FILES):
            self.text[extra], self.data[extra] = _load_yaml(self.data_dir / f"{extra}.yaml")
            self.extra_files[extra] = self.data[extra]
        for stem in list(self.data):
            sp = schema_dir / f"{stem}.yaml"
            if sp.exists():
                _, schema = _load_yaml(sp)
                validate(self.data[stem], schema, f"{stem}.yaml")
            elif stem in FILES:
                raise ParameterError(f"{stem}.yaml has no schema in {schema_dir}")

    def __getitem__(self, stem):
        return self.data[stem]

    def fingerprint(self) -> str:
        return fingerprint({k: self.data[k] for k in sorted(self.data)})
