"""Preset sources: your folder, Ignitron's community collection, and Positive Grid's ToneCloud.

- Your presets are JSON files in ~/Music/Spark Presets, including the dated backup folders.
- The community collection is the song and artist presets in Ignitron's repository
  (github.com/stangreg/Ignitron, BSD-3-Clause), downloaded on request into the user's cache.
- ToneCloud is Positive Grid's preset sharing service. Searching it and downloading a preset
  need no account. The API is undocumented (it is the one the Spark app and Soundshed use), so
  it can change without notice.
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from . import catalog, log
from .preset import Pedal, Preset

LOG = log.get("library")

COMMUNITY_REPO = "stangreg/Ignitron"
COMMUNITY_LIST = f"https://api.github.com/repos/{COMMUNITY_REPO}/contents/data"
CACHE = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "spark40" / "community"
TONECLOUD = "https://api.positivegrid.com/v2"
USER_AGENT = "spark40 (https://github.com/averagenative/0xSpark40)"
TONECLOUD_ORDERS = ("popular", "latest", "alphabet")


def _music_dir() -> Path:
    """The desktop's Music folder (localized names included), falling back to ~/Music."""
    try:
        from gi.repository import GLib
        music = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_MUSIC)
        if music:
            return Path(music)
    except Exception:
        pass
    return Path.home() / "Music"


USER_DIR = _music_dir() / "Spark Presets"
BACKUP_DIR = USER_DIR / "Backups"


def _get(url: str, timeout: float = 20.0) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def safe_name(name: str) -> str:
    cleaned = "".join(c if c.isalnum() or c in " -_.,()&'" else "-" for c in name).strip(" .")
    return cleaned or "Untitled"


# Files

def user_files() -> list[Path]:
    if not USER_DIR.is_dir():
        return []
    return sorted(USER_DIR.rglob("*.json"), key=lambda p: (p.parent != USER_DIR, str(p.parent).lower(), p.name.lower()))


def community_ready() -> bool:
    return CACHE.is_dir() and any(CACHE.glob("*.json"))


def community_files() -> list[Path]:
    return sorted(CACHE.glob("*.json"), key=lambda p: p.name.lower()) if CACHE.is_dir() else []


def download_community(timeout: float = 30.0) -> int:
    """Download Ignitron's preset collection into the cache. Returns the number of presets."""
    listing = json.loads(_get(COMMUNITY_LIST, timeout))
    CACHE.mkdir(parents=True, exist_ok=True)
    count = 0
    for item in listing:
        name = item.get("name", "")
        if not name.endswith(".json") or not item.get("download_url"):
            continue
        data = _get(item["download_url"], timeout)
        try:
            Preset.from_dict(json.loads(data))
        except (ValueError, KeyError, TypeError) as err:
            LOG.info("Skipping community preset %s: %s", name, err)
            continue
        (CACHE / Path(name).name).write_bytes(data)
        count += 1
    LOG.info("Downloaded %d community presets from %s", count, COMMUNITY_REPO)
    return count


REPLACED_DIR = BACKUP_DIR / "Replaced"


def keep_replaced(preset: Preset, number: int) -> Path:
    """Save a stored preset that is about to be overwritten, so it can be put back."""
    from datetime import datetime
    REPLACED_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d %H%M%S")
    path = REPLACED_DIR / f"{stamp} preset {number + 1} - {safe_name(preset.name)}.json"
    preset.save(path)
    return path


def read(path: Path) -> Preset:
    return Preset.from_dict(json.loads(Path(path).read_text()))


# ToneCloud

@dataclass
class CloudPreset:
    id: str
    name: str
    category: str = ""
    creator: str = ""
    description: str = ""
    downloads: int = 0
    likes: int = 0
    effects: list = field(default_factory=list)

    def missing(self, firmware: tuple | None) -> list[str]:
        """Active effects this firmware lacks, judged from the search result alone."""
        bad = []
        for effect in self.effects:
            model = catalog.model(effect)
            if model is None or not model.supported_by(firmware):
                bad.append(effect)
        return bad


def tonecloud_search(keyword: str | None = None, order: str = "popular", page: int = 1,
                     page_size: int = 30, category: str | None = None) -> list[CloudPreset]:
    params = {"preset_for": "spark", "order": order, "page": page, "page_size": page_size}
    if keyword:
        params["keyword"] = keyword
    if category:
        params["category"] = category
    results = json.loads(_get(f"{TONECLOUD}/preset?{urllib.parse.urlencode(params)}"))
    presets = []
    for item in results:
        creator = ((item.get("creator") or {}).get("userprofile") or {}).get("full_name") or ""
        effects = [e for e in (item.get("active_effects") or "").split(",") if e]
        presets.append(CloudPreset(id=item.get("id") or item.get("_id"), name=(item.get("name") or "").strip(),
                                   category=item.get("category") or "", creator=creator.strip(),
                                   description=(item.get("description") or "").strip(),
                                   downloads=int(item.get("num_downloads") or 0), likes=int(item.get("num_likes") or 0),
                                   effects=effects))
    return presets


def tonecloud_preset(preset_id: str) -> Preset:
    """Download one ToneCloud preset and convert it to a Preset."""
    item = json.loads(_get(f"{TONECLOUD}/preset/{urllib.parse.quote(preset_id)}"))
    return from_tonecloud(item)


def from_tonecloud(item: dict) -> Preset:
    data = item.get("preset_data")
    if isinstance(data, str):
        data = json.loads(data)
    if not isinstance(data, dict) or not isinstance(data.get("sigpath"), list):
        raise ValueError("this ToneCloud preset has no signal chain")
    pedals = []
    for block in data["sigpath"]:
        values = {int(p["index"]): float(p["value"]) for p in block.get("params", [])}
        params = [values.get(i, 0.0) for i in range(max(values) + 1)] if values else []
        pedals.append(Pedal(str(block.get("dspId", "")), bool(block.get("active")), params))
    if len(pedals) != len(catalog.SLOTS):
        raise ValueError(f"this ToneCloud preset has {len(pedals)} blocks; the Spark 40 needs {len(catalog.SLOTS)}")
    meta = data.get("meta") or {}
    preset = Preset(name=(item.get("name") or meta.get("name") or "ToneCloud preset").strip(), pedals=pedals,
                    description=(item.get("description") or meta.get("description") or "").strip()[:200],
                    icon=meta.get("icon") or "icon.png", bpm=float(data.get("bpm") or 120.0))
    if meta.get("id"):
        preset.uuid = str(meta["id"]).upper()
    return preset
