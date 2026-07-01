import ctypes
import threading
import traceback
from dataclasses import dataclass
from pathlib import Path
from tkinter import BOTH, DISABLED, END, LEFT, NORMAL, RIGHT, WORD, Button, Canvas, Frame, Label, StringVar, Text, Tk, Toplevel, messagebox
from tkinter.ttk import Combobox, Progressbar

from PIL import Image, ImageGrab, ImageTk


APP_TITLE = "屏幕文字翻译"
TARGET_LANGUAGE = "zh-CN"
LANGUAGE_OPTIONS = {
    "英语": {"ocr": ["en"], "translator": "en"},
    "阿拉伯语": {"ocr": ["ar"], "translator": "ar"},
    "日语": {"ocr": ["ja", "en"], "translator": "ja"},
}


def enable_dpi_awareness():
    """Keep Tk mouse coordinates aligned with real screen pixels on Windows."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


@dataclass
class CaptureArea:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    def as_bbox(self) -> tuple[int, int, int, int]:
        return self.left, self.top, self.right, self.bottom


class SelectionOverlay:
    def __init__(self, parent: Tk, on_done):
        self.parent = parent
        self.on_done = on_done
        self.start_x = 0
        self.start_y = 0
        self.rect_id = None

        self.window = Toplevel(parent)
        self.window.title("选择屏幕区域")
        self.window.attributes("-fullscreen", True)
        self.window.attributes("-topmost", True)
        self.window.attributes("-alpha", 0.28)
        self.window.configure(bg="#0f172a")
        self.window.cursor = "crosshair"

        self.canvas = Canvas(self.window, bg="#0f172a", highlightthickness=0, cursor="crosshair")
        self.canvas.pack(fill=BOTH, expand=True)
        self.canvas.create_text(
            40,
            36,
            anchor="w",
            fill="white",
            font=("Microsoft YaHei", 18, "bold"),
            text="拖拽框选要翻译的屏幕区域，松开鼠标完成；按 Esc 取消",
        )

        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.window.bind("<Escape>", self.cancel)
        self.window.bind_all("<Escape>", self.cancel)
        self.window.protocol("WM_DELETE_WINDOW", self.cancel)
        self.window.focus_force()

    def on_press(self, event):
        self.start_x = self.window.winfo_pointerx()
        self.start_y = self.window.winfo_pointery()
        if self.rect_id:
            self.canvas.delete(self.rect_id)
        self.rect_id = self.canvas.create_rectangle(
            event.x,
            event.y,
            event.x,
            event.y,
            outline="#38bdf8",
            width=4,
            fill="#e0f2fe",
            stipple="gray25",
        )

    def on_drag(self, event):
        if not self.rect_id:
            return
        root_x = self.window.winfo_rootx()
        root_y = self.window.winfo_rooty()
        current_x = self.window.winfo_pointerx()
        current_y = self.window.winfo_pointery()
        self.canvas.coords(
            self.rect_id,
            self.start_x - root_x,
            self.start_y - root_y,
            current_x - root_x,
            current_y - root_y,
        )

    def on_release(self, _event):
        end_x = self.window.winfo_pointerx()
        end_y = self.window.winfo_pointery()
        left, right = sorted((self.start_x, end_x))
        top, bottom = sorted((self.start_y, end_y))

        if right - left < 20 or bottom - top < 20:
            messagebox.showwarning("区域太小", "请至少框选 20x20 像素的区域。")
            self.cancel()
            return

        self.close_overlay()
        self.on_done(CaptureArea(left, top, right, bottom))

    def close_overlay(self):
        self.window.unbind_all("<Escape>")
        self.window.destroy()

    def cancel(self, _event=None):
        self.close_overlay()
        self.parent.deiconify()
        self.parent.lift()


class ArabicScreenTranslatorApp:
    def __init__(self):
        self.root = Tk()
        self.root.title(APP_TITLE)
        self.root.geometry("980x720")
        self.root.minsize(860, 620)

        self.area: CaptureArea | None = None
        self.captured_image: Image.Image | None = None
        self.preview_image = None
        self.ocr_readers = {}
        self.language_var = StringVar(value="阿拉伯语")
        self.status = StringVar(value="先选择画面文字语言，再框选要翻译的屏幕区域。")

        self.build_ui()

    def build_ui(self):
        top = Frame(self.root, padx=18, pady=16)
        top.pack(fill="x")

        Label(top, text=APP_TITLE, font=("Microsoft YaHei", 22, "bold")).pack(anchor="w")
        Label(
            top,
            text="选择画面文字语言后框选屏幕区域，点击确认即可识别并翻译成中文。",
            fg="#475569",
            font=("Microsoft YaHei", 10),
        ).pack(anchor="w", pady=(4, 0))

        button_bar = Frame(self.root, padx=18)
        button_bar.pack(fill="x")
        Label(button_bar, text="画面语言：", font=("Microsoft YaHei", 10)).pack(side=LEFT, padx=(0, 6))
        self.language_combo = Combobox(
            button_bar,
            textvariable=self.language_var,
            values=list(LANGUAGE_OPTIONS.keys()),
            state="readonly",
            width=10,
        )
        self.language_combo.pack(side=LEFT, padx=(0, 12))
        self.language_combo.bind("<<ComboboxSelected>>", self.on_language_changed)

        Button(button_bar, text="选择屏幕区域", command=self.select_area, width=16, height=2).pack(side=LEFT)
        self.translate_button = Button(button_bar, text="确认并翻译", command=self.translate_selected_area, width=16, height=2, state=DISABLED)
        self.translate_button.pack(side=LEFT, padx=10)
        Button(button_bar, text="清空结果", command=self.clear_result, width=12, height=2).pack(side=LEFT)

        self.progress = Progressbar(button_bar, mode="indeterminate", length=210)
        self.progress.pack(side=RIGHT, padx=10)

        Label(self.root, textvariable=self.status, fg="#2563eb", anchor="w", padx=18, pady=8).pack(fill="x")

        body = Frame(self.root, padx=18, pady=10)
        body.pack(fill=BOTH, expand=True)

        left_panel = Frame(body)
        left_panel.pack(side=LEFT, fill=BOTH, expand=True, padx=(0, 10))
        right_panel = Frame(body)
        right_panel.pack(side=RIGHT, fill=BOTH, expand=True, padx=(10, 0))

        Label(left_panel, text="截图预览", font=("Microsoft YaHei", 12, "bold")).pack(anchor="w")
        self.preview_label = Label(left_panel, text="尚未选择区域", bg="#f1f5f9", fg="#64748b", width=46, height=18)
        self.preview_label.pack(fill=BOTH, expand=True, pady=(8, 14))

        Label(left_panel, text="识别到的原文", font=("Microsoft YaHei", 12, "bold")).pack(anchor="w")
        self.source_text = Text(left_panel, wrap=WORD, height=8, font=("Arial", 12))
        self.source_text.pack(fill=BOTH, expand=True, pady=(8, 0))

        Label(right_panel, text="中文翻译", font=("Microsoft YaHei", 12, "bold")).pack(anchor="w")
        self.translation_text = Text(right_panel, wrap=WORD, font=("Microsoft YaHei", 12))
        self.translation_text.pack(fill=BOTH, expand=True, pady=(8, 0))

    def select_area(self):
        self.root.withdraw()
        self.root.update_idletasks()
        self.root.after(450, lambda: SelectionOverlay(self.root, self.on_area_selected))

    def on_language_changed(self, _event=None):
        language_name = self.language_var.get()
        self.status.set(f"当前画面语言：{language_name}。框选区域后点击“确认并翻译”。")

    def on_area_selected(self, area: CaptureArea):
        self.area = area
        self.captured_image = None
        self.root.withdraw()
        self.root.update_idletasks()
        self.root.after(650, self.capture_after_selection)

    def capture_after_selection(self):
        if not self.area:
            self.root.deiconify()
            self.root.lift()
            return

        try:
            self.captured_image = self.capture_area_image()
            self.root.deiconify()
            self.root.lift()
            self.translate_button.configure(state=NORMAL)
            self.status.set(f"已选择区域：{self.area.width} x {self.area.height}。点击“确认并翻译”开始识别。")
            self.update_preview()
        except Exception as exc:
            self.root.deiconify()
            self.root.lift()
            self.translate_button.configure(state=DISABLED)
            self.preview_label.configure(image="", text="截图预览失败", bg="#f1f5f9")
            self.status.set(f"截图失败：{exc}")

    def update_preview(self):
        if not self.captured_image:
            return
        try:
            preview = self.captured_image.copy()
            preview.thumbnail((430, 260))
            self.preview_image = ImageTk.PhotoImage(preview)
            self.preview_label.configure(image=self.preview_image, text="", bg="#ffffff")
        except Exception as exc:
            self.preview_label.configure(image="", text="截图预览失败")
            self.status.set(f"截图预览失败：{exc}")

    def capture_area_image(self) -> Image.Image:
        if not self.area:
            raise RuntimeError("尚未选择截图区域")

        try:
            import mss

            with mss.mss() as screenshot_tool:
                shot = screenshot_tool.grab(
                    {
                        "left": self.area.left,
                        "top": self.area.top,
                        "width": self.area.width,
                        "height": self.area.height,
                    }
                )
            return Image.frombytes("RGB", shot.size, shot.rgb)
        except Exception:
            return ImageGrab.grab(bbox=self.area.as_bbox())

    def translate_selected_area(self):
        if not self.area:
            messagebox.showinfo("未选择区域", "请先点击“选择屏幕区域”。")
            return

        language_name = self.language_var.get()
        self.set_busy(True, f"正在截图、识别{language_name}并翻译成中文，请稍等...")
        worker = threading.Thread(target=self.run_ocr_and_translation, args=(language_name,), daemon=True)
        worker.start()

    def run_ocr_and_translation(self, language_name: str):
        try:
            if self.captured_image is None:
                image = self.capture_area_image()
            else:
                image = self.captured_image.copy()
            image_path = Path(__file__).with_name("latest_capture.png")
            image.save(image_path)

            language_config = LANGUAGE_OPTIONS[language_name]
            ocr_key = tuple(language_config["ocr"])
            if ocr_key not in self.ocr_readers:
                import easyocr

                self.ocr_readers[ocr_key] = easyocr.Reader(language_config["ocr"], gpu=False)

            import numpy as np

            # Avoid cv2.imread on non-ASCII paths such as E:\飞燕\..., which can return None.
            result = self.ocr_readers[ocr_key].readtext(np.array(image), detail=0, paragraph=True)
            source_text = "\n".join(part.strip() for part in result if part.strip())

            if not source_text:
                self.root.after(0, lambda: self.show_result("", f"没有识别到{language_name}，请重新框选更清晰的区域。", False))
                return

            from deep_translator import GoogleTranslator

            translated = GoogleTranslator(source=language_config["translator"], target=TARGET_LANGUAGE).translate(source_text)
            self.root.after(0, lambda: self.show_result(source_text, translated, True))
        except Exception:
            error = traceback.format_exc()
            self.root.after(0, lambda: self.show_result("", f"处理失败：\n{error}", False))

    def show_result(self, source_text: str, translated_text: str, success: bool):
        self.source_text.delete("1.0", END)
        self.translation_text.delete("1.0", END)
        self.source_text.insert("1.0", source_text)
        self.translation_text.insert("1.0", translated_text)
        self.set_busy(False, "翻译完成。" if success else "未完成，请查看提示信息。")

    def clear_result(self):
        self.source_text.delete("1.0", END)
        self.translation_text.delete("1.0", END)
        self.preview_label.configure(image="", text="尚未选择区域", bg="#f1f5f9")
        self.preview_image = None
        self.captured_image = None
        self.area = None
        self.translate_button.configure(state=DISABLED)
        self.status.set("先选择画面文字语言，再框选要翻译的屏幕区域。")

    def set_busy(self, busy: bool, status: str):
        self.status.set(status)
        self.translate_button.configure(state=DISABLED if busy else (NORMAL if self.area else DISABLED))
        if busy:
            self.progress.start(12)
        else:
            self.progress.stop()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    enable_dpi_awareness()
    ArabicScreenTranslatorApp().run()
