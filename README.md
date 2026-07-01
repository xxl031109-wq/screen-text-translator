# 屏幕文字翻译工具

这是一个独立桌面应用，用来框选电脑屏幕中的一块区域，点击确认后识别画面里的文字并翻译成中文。

当前支持识别语言：

- 英语
- 阿拉伯语
- 日语

## 安装依赖

```powershell
cd screen-text-translator
python -m pip install -r requirements.txt
```

也可以双击 `install.bat` 自动安装。

第一次使用某个语言时，EasyOCR 会下载对应识别模型，需要联网，耗时会比较久。

## 运行

```powershell
cd screen-text-translator
python app.py
```

也可以双击 `run.bat`。

## 打包成 exe

```powershell
cd screen-text-translator
.\build_exe.bat
```

打包完成后，程序会在 `dist\ArabicScreenTranslator.exe`。注意：EasyOCR/PyTorch 体积较大，exe 文件会比较大，首次识别仍可能下载模型。

## 使用步骤

1. 在 `画面语言` 下拉框选择英语、阿拉伯语或日语。
2. 点击 `选择屏幕区域`。
3. 在屏幕上拖拽框选包含对应语言文字的画面。
4. 回到主窗口后点击 `确认并翻译`。
5. 左侧显示识别到的原文，右侧显示中文翻译。

## 说明

- OCR 使用 EasyOCR 的英语、阿拉伯语、日语模型。
- 翻译使用 `deep-translator` 的 GoogleTranslator，需要网络。
- 当前默认翻译方向为所选语言到中文。
