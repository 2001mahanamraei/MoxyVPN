"""Connect / disconnect sound + short animation (taken from the promo motion clip).

Frames are small JPEGs in assets/fx/<clip>/NNN.jpg, sound is assets/fx/<clip>.wav.
Everything is best-effort: if Pillow or winsound is missing the app just carries on silently.
"""
import glob
import os

FPS = 15


class FX:
    def __init__(self, root, canvas, assets, pos=(200, 215)):
        self.root, self.c, self.dir, self.pos = root, canvas, os.path.join(assets, "fx"), pos
        self.frames = {}
        self.item = None
        self.job = None
        self.enabled = True
        root.after(800, self._preload)

    def rebind(self, canvas):
        """The canvas is rebuilt on theme change."""
        self.cancel()
        self.c = canvas

    def _preload(self):
        try:
            from PIL import Image, ImageTk
        except ImportError:
            return
        for clip in ("connect", "disconnect"):
            files = sorted(glob.glob(os.path.join(self.dir, clip, "*.jpg")))
            try:
                self.frames[clip] = [ImageTk.PhotoImage(Image.open(f)) for f in files]
            except Exception:
                self.frames[clip] = []

    def _sound(self, clip):
        try:
            import winsound
            winsound.PlaySound(os.path.join(self.dir, clip + ".wav"),
                               winsound.SND_FILENAME | winsound.SND_ASYNC)
        except Exception:
            pass

    def play(self, clip):
        if not self.enabled:
            return
        self.cancel()
        self._sound(clip)
        frames = self.frames.get(clip)
        if frames:
            self.item = self.c.create_image(*self.pos, image=frames[0], tags="fx")
            self.c.tag_raise("fx")
            self._step(clip, 1)

    def _step(self, clip, i):
        frames = self.frames[clip]
        if i >= len(frames):
            self.cancel(sound=False)
            return
        self.c.itemconfig(self.item, image=frames[i])
        self.job = self.root.after(1000 // FPS, self._step, clip, i + 1)

    def cancel(self, sound=True):
        if self.job:
            self.root.after_cancel(self.job)
            self.job = None
        if self.item:
            try:
                self.c.delete(self.item)
            except Exception:
                pass
            self.item = None
        if sound:
            try:
                import winsound
                winsound.PlaySound(None, winsound.SND_PURGE)
            except Exception:
                pass
