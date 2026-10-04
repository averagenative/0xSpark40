"""Presets dialog: your preset files, ToneCloud search, and the community collection.

Clicking a preset plays it on the amp without touching the four stored presets. Network calls
run on short-lived threads and report back on the GLib main loop.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402

from .. import catalog, library, log  # noqa: E402
from ..preset import Preset  # noqa: E402
from ..protocol import firmware_text  # noqa: E402
from . import settings  # noqa: E402

LOG = log.get("presets")
ORDER_LABELS = {"popular": "Most downloaded", "latest": "Newest", "alphabet": "A to Z"}


def run_async(work, done) -> None:
    """Run ``work()`` on a thread and call ``done(result, error)`` on the main loop."""
    def target():
        try:
            result, error = work(), None
        except Exception as err:   # network and parse errors go back to the UI
            result, error = None, err
        GLib.idle_add(lambda: done(result, error) and False)
    threading.Thread(target=target, daemon=True).start()


def esc(text: str) -> str:
    return GLib.markup_escape_text(text or "")


def chain_text(preset: Preset) -> str:
    return ", ".join(p.name for p in preset.pedals if p.on and p.id != catalog.REVERB) or "everything off"


class PresetsDialog(Adw.Dialog):
    def __init__(self, window):
        super().__init__(title="Presets", content_width=680, content_height=720)
        self.window = window
        self.firmware = window.state.firmware if window.state else None
        view = Adw.ToolbarView()
        header = Adw.HeaderBar()
        self.stack = Adw.ViewStack()
        switcher = Adw.ViewSwitcher(stack=self.stack, policy=Adw.ViewSwitcherPolicy.WIDE)
        header.set_title_widget(switcher)
        open_button = Gtk.Button(icon_name="document-open-symbolic", tooltip_text="Load a preset file from anywhere")
        open_button.connect("clicked", self._open_file)
        header.pack_start(open_button)
        view.add_top_bar(header)
        self.toasts = Adw.ToastOverlay(child=self.stack)
        view.set_content(self.toasts)
        self.set_child(view)

        self.stack.add_titled_with_icon(self._build_yours(), "yours", "Yours", "folder-music-symbolic")
        self.stack.add_titled_with_icon(self._build_cloud(), "cloud", "ToneCloud", "weather-overcast-symbolic")
        self.stack.add_titled_with_icon(self._build_community(), "community", "Community", "system-users-symbolic")
        self.refresh()

    # Shared

    def toast(self, text: str) -> None:
        self.toasts.add_toast(Adw.Toast(title=text, timeout=3))

    def play(self, preset: Preset) -> None:
        if self.window.state is None:
            self.toast("Connect the amp to play a preset.")
            return
        bad = preset.unsupported(self.firmware)
        if bad:
            self.toast(f"This amp's firmware lacks {', '.join(bad)}, so loading it could crash the amp.")
            return
        self.window.load_preset(preset, preset.name)

    def save_to_library(self, preset: Preset, folder: str) -> Path:
        target = library.USER_DIR / folder
        target.mkdir(parents=True, exist_ok=True)
        path = target / f"{library.safe_name(preset.name)}.json"
        preset.save(path)
        self.toast(f"Saved to {path.parent.name}: {preset.name}")
        return path

    def preset_row(self, preset: Preset | None, title: str, subtitle: str, on_play, error: str | None = None,
                   on_save=None) -> Adw.ActionRow:
        row = Adw.ActionRow(title=esc(title), activatable=error is None)
        bad = preset.unsupported(self.firmware) if preset else []
        if error:
            row.set_subtitle(esc(error))
            row.set_sensitive(False)
        elif bad:
            fw = firmware_text(self.firmware) if self.firmware else "this amp"
            row.set_subtitle(esc(f"Needs newer firmware than {fw}: {', '.join(bad)}"))
            row.set_sensitive(False)
        else:
            row.set_subtitle(esc(subtitle))
            row.connect("activated", lambda _r: on_play())
            row.add_suffix(Gtk.Image(icon_name="media-playback-start-symbolic", tooltip_text="Play on the amp"))
        if on_save and not error and not bad:
            save = Gtk.Button(icon_name="document-save-symbolic", valign=Gtk.Align.CENTER,
                              tooltip_text="Save to your presets")
            save.add_css_class("flat")
            save.connect("clicked", lambda _b: on_save())
            row.add_suffix(save)
        return row

    def refresh(self) -> None:
        self._fill_yours()
        self._fill_community()

    # Yours

    def _build_yours(self) -> Gtk.Widget:
        page = Adw.PreferencesPage()
        actions = Adw.PreferencesGroup()
        self.name_row = Adw.EntryRow(title="Save the current sound as", show_apply_button=True)
        self.name_row.connect("apply", self._save_current)
        actions.add(self.name_row)
        backup = Adw.ButtonRow(title="Back up the amp's four presets", start_icon_name="document-save-symbolic")
        backup.connect("activated", self._backup)
        actions.add(backup)
        keep = Adw.SwitchRow(title="Keep my amp volume",
                             subtitle="Play a preset's sound with the current amp Volume, so a loud preset doesn't "
                                      "jump out", active=bool(self.window.prefs.get("keep_volume", True)))
        keep.connect("notify::active", self._keep_changed)
        actions.add(keep)
        page.add(actions)
        self.yours = Adw.PreferencesGroup(
            title="Your presets", description=f"Click a preset to play it on the amp. Files live in {library.USER_DIR}.")
        page.add(self.yours)
        self._your_rows: list = []
        return page

    def _fill_yours(self) -> None:
        for row in self._your_rows:
            self.yours.remove(row)
        self._your_rows = []
        paths = library.user_files()
        if not paths:
            row = Adw.ActionRow(title="No presets yet",
                                subtitle="Save the current sound, back up the amp, or save presets from ToneCloud "
                                         "and the community collection")
            self.yours.add(row)
            self._your_rows.append(row)
        for path in paths:
            try:
                preset = library.read(path)
            except (OSError, ValueError, KeyError, TypeError) as err:
                row = self.preset_row(None, path.stem, "", None, error=f"Can't read: {err}")
            else:
                where = str(path.parent.relative_to(library.USER_DIR))
                subtitle = chain_text(preset) if where == "." else f"{where}: {chain_text(preset)}"
                row = self.preset_row(preset, preset.name, subtitle, lambda p=preset: self.play(p))
            self.yours.add(row)
            self._your_rows.append(row)

    def _save_current(self, row) -> None:
        name = row.get_text().strip()
        if not name or self.window.state is None:
            return
        library.USER_DIR.mkdir(parents=True, exist_ok=True)
        self.window.worker.submit("save_file", library.USER_DIR / f"{library.safe_name(name)}.json", name)
        row.set_text("")

    def _backup(self, _row) -> None:
        if self.window.state is None:
            self.toast("Connect the amp to back up its presets.")
            return
        self.window.apply_status.busy("Backing up the amp's presets...")
        self.window.worker.submit("backup", library.BACKUP_DIR)

    def _keep_changed(self, row, _pspec) -> None:
        self.window.prefs["keep_volume"] = row.get_active()
        settings.save(self.window.prefs)

    # ToneCloud

    def _build_cloud(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        bar = Gtk.Box(spacing=8, margin_top=12, margin_bottom=6, margin_start=12, margin_end=12)
        self.search = Gtk.SearchEntry(placeholder_text="Search ToneCloud: song, artist, or style", hexpand=True)
        self.search.connect("activate", lambda _e: self._cloud_search(new=True))
        self.order = Gtk.DropDown.new_from_strings(list(ORDER_LABELS.values()))
        self.order.update_property([Gtk.AccessibleProperty.LABEL], ["Sort order"])
        self.order.connect("notify::selected", lambda *_: self._cloud_search(new=True))
        bar.append(self.search)
        bar.append(self.order)
        box.append(bar)
        note = Gtk.Label(label="Presets shared on Positive Grid's ToneCloud. Searching needs no account. Presets "
                               "that use models this amp's firmware lacks are greyed out.",
                         xalign=0, wrap=True, margin_start=14, margin_end=14, margin_bottom=6)
        note.add_css_class("caption")
        note.add_css_class("dim-label")
        box.append(note)
        self.cloud_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, margin_start=12, margin_end=12,
                                      margin_bottom=12)
        self.cloud_list.add_css_class("boxed-list")
        self.cloud_more = Gtk.Button(label="Show more", halign=Gtk.Align.CENTER, margin_bottom=12, visible=False)
        self.cloud_more.connect("clicked", lambda _b: self._cloud_search(new=False))
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        inner.append(self.cloud_list)
        inner.append(self.cloud_more)
        box.append(Gtk.ScrolledWindow(child=inner, vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER))
        self._cloud_page = 1
        self._cloud_loaded = False
        self._cloud_generation = 0
        self.stack.connect("notify::visible-child-name", self._tab_changed)
        return box

    def _tab_changed(self, stack, _pspec) -> None:
        if stack.get_visible_child_name() == "cloud" and not self._cloud_loaded:
            self._cloud_search(new=True)

    def _cloud_search(self, new: bool) -> None:
        self._cloud_loaded = True
        if new:
            self._cloud_generation += 1
            self._cloud_page = 1
            while (child := self.cloud_list.get_first_child()) is not None:
                self.cloud_list.remove(child)
        generation = self._cloud_generation
        keyword = self.search.get_text().strip() or None
        order = list(ORDER_LABELS)[self.order.get_selected()]
        page = self._cloud_page
        spinner = Adw.ActionRow(title="Searching ToneCloud...")
        spinner.add_prefix(Adw.Spinner())
        self.cloud_list.append(spinner)
        self.cloud_more.set_visible(False)

        def done(results, error):
            if generation != self._cloud_generation:
                return      # a newer search replaced this one
            self.cloud_list.remove(spinner)
            if error is not None:
                LOG.warning("ToneCloud search failed: %s", error)
                self.cloud_list.append(Adw.ActionRow(title="Couldn't reach ToneCloud", subtitle=esc(str(error))))
                return
            if not results and page == 1:
                self.cloud_list.append(Adw.ActionRow(title="No presets found"))
            for item in results:
                self.cloud_list.append(self._cloud_row(item))
            self._cloud_page = page + 1
            self.cloud_more.set_visible(len(results) >= 30)

        run_async(lambda: library.tonecloud_search(keyword, order=order, page=page), done)

    def _cloud_row(self, item: library.CloudPreset) -> Adw.ActionRow:
        details = [item.category, f"by {item.creator}" if item.creator else "", f"{item.downloads:,} downloads"]
        subtitle = ", ".join(d for d in details if d)
        missing = item.missing(self.firmware)
        row = Adw.ActionRow(title=esc(item.name or "Untitled"), activatable=not missing)
        if missing:
            row.set_subtitle(esc(f"Uses models this firmware lacks: {', '.join(missing)}"))
            row.set_sensitive(False)
            return row
        row.set_subtitle(esc(subtitle))
        row.set_tooltip_text(item.description or None)
        row.add_suffix(Gtk.Image(icon_name="media-playback-start-symbolic", tooltip_text="Play on the amp"))
        save = Gtk.Button(icon_name="document-save-symbolic", valign=Gtk.Align.CENTER,
                          tooltip_text="Save to your presets")
        save.add_css_class("flat")
        save.connect("clicked", lambda _b: self._cloud_fetch(item, save=True))
        row.add_suffix(save)
        row.connect("activated", lambda _r: self._cloud_fetch(item, save=False))
        return row

    def _cloud_fetch(self, item: library.CloudPreset, save: bool) -> None:
        self.window.apply_status.busy(f"Downloading '{item.name}' from ToneCloud...")

        def done(preset, error):
            if error is not None:
                LOG.warning("ToneCloud download failed: %s", error)
                self.window.apply_status.done(f"Couldn't download '{item.name}'")
                self.toast(f"Couldn't download that preset: {error}")
                return
            if save:
                self.window.apply_status.done(f"Downloaded '{preset.name}'")
                if preset.unsupported(self.firmware):
                    self.toast("Saved, but this amp's firmware lacks a model in it.")
                self.save_to_library(preset, "ToneCloud")
                self._fill_yours()
            else:
                self.play(preset)

        run_async(lambda: library.tonecloud_preset(item.id), done)

    # Community

    def _build_community(self) -> Gtk.Widget:
        page = Adw.PreferencesPage()
        intro = Adw.PreferencesGroup(
            title="Community presets",
            description="Song and artist presets collected by the Ignitron project "
                        "(github.com/stangreg/Ignitron, BSD-3-Clause), downloaded to your computer.")
        self.download_row = Adw.ButtonRow(title="Download the collection", start_icon_name="folder-download-symbolic")
        self.download_row.connect("activated", self._download_community)
        intro.add(self.download_row)
        page.add(intro)
        self.community = Adw.PreferencesGroup()
        page.add(self.community)
        self._community_rows: list = []
        return page

    def _fill_community(self) -> None:
        for row in self._community_rows:
            self.community.remove(row)
        self._community_rows = []
        ready = library.community_ready()
        self.download_row.set_title("Download again for updates" if ready else "Download the collection")
        for path in library.community_files():
            try:
                preset = library.read(path)
            except (OSError, ValueError, KeyError, TypeError) as err:
                row = self.preset_row(None, path.stem, "", None, error=f"Can't read: {err}")
            else:
                subtitle = preset.description or chain_text(preset)
                row = self.preset_row(preset, preset.name, subtitle, lambda p=preset: self.play(p),
                                      on_save=lambda p=preset: (self.save_to_library(p, "Community"),
                                                                self._fill_yours()))
            self.community.add(row)
            self._community_rows.append(row)

    def _download_community(self, row) -> None:
        row.set_sensitive(False)
        row.set_title("Downloading...")

        def done(count, error):
            row.set_sensitive(True)
            if error is not None:
                LOG.warning("Community download failed: %s", error)
                self.toast(f"Couldn't download the collection: {error}")
            else:
                self.toast(f"Downloaded {count} presets")
            self._fill_community()

        run_async(library.download_community, done)

    # Files from anywhere

    def _open_file(self, _button) -> None:
        dialog = Gtk.FileDialog(title="Open a preset")
        json_filter = Gtk.FileFilter(name="Spark presets (JSON)")
        json_filter.add_pattern("*.json")
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(json_filter)
        dialog.set_filters(filters)
        if library.USER_DIR.is_dir():
            dialog.set_initial_folder(Gio.File.new_for_path(str(library.USER_DIR)))

        def done(source, result):
            try:
                file = source.open_finish(result)
            except GLib.Error:
                return
            try:
                preset = Preset.from_dict(json.loads(Path(file.get_path()).read_text()))
            except (OSError, ValueError, KeyError, TypeError) as err:
                self.toast(f"Couldn't read that preset: {err}")
                return
            self.play(preset)

        dialog.open(self.window, None, done)
