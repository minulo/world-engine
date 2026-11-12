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
        if schema.get("finite") and value in (float("inf"), float("-inf")):
            problems.append(f"{where}: is infinite; it must be a finite number")
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


_MERGE = "tag:yaml.org,2002:merge"


def _refuse_keys_written_twice(text):
    """Plain YAML keeps the last of two equal keys in one map and says nothing, so that a constant set twice in a
    long file would silently take its second value. This walks the file as it is written, before anything is
    built from it: a key taken over from an anchor with "<<" and then set again is a legal override, not a key
    written twice, and merges may be chained."""
    loader = yaml.SafeLoader(text)
    try:
        root = loader.get_single_node()
        seen, todo = set(), [root] if root is not None else []
        while todo:
            node = todo.pop()
            if id(node) in seen:                             # an anchor used in several places is one node
                continue
            seen.add(id(node))
            if isinstance(node, yaml.MappingNode):
                keys = set()
                for key_node, value_node in node.value:
                    if key_node.tag != _MERGE and isinstance(key_node, yaml.ScalarNode):
                        key = loader.construct_object(key_node, deep=True)
                        if key in keys:
                            raise yaml.constructor.ConstructorError(None, None, f"the key {key!r} is written twice in one map",
                                                                    key_node.start_mark)
                        keys.add(key)
                    todo += [key_node, value_node]
            elif isinstance(node, yaml.SequenceNode):
                todo += node.value
    finally:
        loader.dispose()


def load_yaml_text(text, name):
    """Parse one YAML text with the engine's rules; `name` is what a refusal calls it."""
    try:
        _refuse_keys_written_twice(text)
        return yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise ParameterError(f"{name}: not valid YAML: {e}") from None


def _load_yaml(path: Path):
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ParameterError(f"{path.name}: the file is missing from {path.parent}") from None
    return text, load_yaml_text(text, path.name)


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


FANTASY_DIR = "fantasy"         # data/fantasy/<name>.yaml: invented layers, laid over the files only when asked for


def fantasy_layers(data_dir=DEFAULT_DATA_DIR) -> list:
    """The names of the fantasy layers a data directory offers (with the engine's own where it has none)."""
    found = {p.stem for d in (Path(data_dir) / FANTASY_DIR, DEFAULT_DATA_DIR / FANTASY_DIR) if d.is_dir() for p in d.glob("*.yaml")}
    return sorted(found)


def _added(base, adds, where):
    """The base with the entries of a fantasy layer added, key by key. A layer only adds: a key it names that the base
    holds already must be a map on both sides, and is entered; anything else would change the real physics."""
    out = dict(base or {})
    for k, v in (adds or {}).items():
        if k not in out:
            out[k] = v
        elif isinstance(v, dict) and isinstance(out[k], dict):
            out[k] = _added(out[k], v, f"{where}.{k}")
        else:
            raise ParameterError(f"{where}.{k}: the fantasy layer would change this entry, which the parameter files hold "
                                 f"already; a fantasy layer only adds to them")
    return out


class Parameters:
    """All parameter files of one data directory, checked against their schemas.

    `data` maps a file's stem to its parsed content; `text` keeps each file exactly as written,
    so that a world store can hold a full copy of what made it.

    `fantasy` names invented layers (data/fantasy/<name>.yaml) to lay over the files. A layer only adds entries; the
    files it adds to keep the text of what they became, and models.yaml lists the layers under `fantasy`, so that a
    world store's own copy of its parameters says which layers made it and rebuilds the same engine.
    """

    def __init__(self, data_dir, overrides: dict | None = None, fantasy=()):
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
        if isinstance(fantasy, str):
            fantasy = (fantasy,)
        fantasy = list(fantasy)
        for name in fantasy:
            if fantasy.count(name) > 1:
                raise ParameterError(f"the fantasy layer {name} is named twice; a layer is laid over the files once")
        for name in fantasy:
            if name not in self.fantasy:                     # (a layer named earlier may have needed it, and laid it)
                self._lay_over(name, schema_dir)
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

    def _lay_over(self, name, schema_dir, needed_by=()):
        """Add the entries of the fantasy layer `name` to the parameter files, after the layers it needs: a layer that
        builds on another names it under `needs`, and that one is laid first if it is not laid yet."""
        offered = fantasy_layers(self.data_dir)
        if not isinstance(name, str) or name not in offered:
            asked = f", which the layer {needed_by[-1]} needs" if needed_by else ""
            raise ParameterError(f"there is no fantasy layer named {name!r}{asked} (there are: {', '.join(offered) or 'none'})")
        if name in needed_by:
            raise ParameterError(f"the fantasy layers {' and '.join(needed_by)} need each other; one of them must come first")
        path = self.data_dir / FANTASY_DIR / f"{name}.yaml"
        if not path.exists():
            path = DEFAULT_DATA_DIR / FANTASY_DIR / f"{name}.yaml"
        where = f"{FANTASY_DIR}/{name}.yaml"
        _, layer = _load_yaml(path)
        schema = schema_dir / "fantasy.yaml"
        validate(layer, _load_yaml(schema if schema.exists() else DEFAULT_DATA_DIR / "schemas" / "fantasy.yaml")[1], where)
        for other in layer.get("needs") or []:
            if other not in self.fantasy:
                self._lay_over(other, schema_dir, tuple(needed_by) + (name,))
        for stem, adds in layer["adds"].items():
            if stem not in FILES:
                raise ParameterError(f"{where}: adds to {stem}, which is not one of the parameter files ({', '.join(FILES)})")
            self.data[stem] = _added(self.data[stem], adds, f"{where}: {stem}")
        self.data["models"] = {**self.data["models"], "fantasy": self.fantasy + [name]}
        for stem in set(layer["adds"]) | {"models"}:
            self.text[stem] = yaml.safe_dump(self.data[stem], sort_keys=False)

    @property
    def fantasy(self) -> list:
        """The fantasy layers laid over these files, in the order they were laid."""
        return list((self.data.get("models") or {}).get("fantasy") or [])

    def __getitem__(self, stem):
        return self.data[stem]

    def fingerprint(self) -> str:
        return fingerprint({k: self.data[k] for k in sorted(self.data)})
