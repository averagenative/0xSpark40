"""Render the presets window's ToneCloud tab in demo mode to a PNG: screenshot-presets.py OUT.png"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gi.repository import Gio, GLib  # noqa: E402

from spark40.gui import app as appmod  # noqa: E402
from spark40.gui.demo import DemoWorker  # noqa: E402

OUT = sys.argv[1]


class Shot(appmod.SparkApplication):
    def do_activate(self):
        window = appmod.SparkWindow(self, worker_class=DemoWorker)
        window.set_default_size(1280, 940)
        window.present()

        def open_presets():
            window._show_presets(None)
            dialog = window.presets_dialog
            dialog.search.set_text("dire straits")
            dialog.stack.set_visible_child_name("cloud")
            dialog._cloud_search(new=True)
            return GLib.SOURCE_REMOVE

        def shoot():
            appmod.save_png(window, OUT, window)
            window.close()
            return GLib.SOURCE_REMOVE

        GLib.timeout_add(800, open_presets)
        GLib.timeout_add(6000, shoot)


app = Shot(demo=True)
app.set_flags(app.get_flags() | Gio.ApplicationFlags.NON_UNIQUE)
app.run([sys.argv[0]])
