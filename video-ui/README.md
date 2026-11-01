# W2 周视频录制台

这是与主线交付界面 `web/` 分离的录屏专用前端。它只负责讲清楚 W1 和 W2 做了什么、为什么做、得到了什么结果，不替代正式交付页面，也不进入现有 W02 交付包。

## 生成

在仓库根目录运行：

```powershell
$env:PYTHONUTF8='1'
D:\python\python.exe scripts\build_video_ui.py
```

生成物：

- `video-ui/src/story.json`：唯一语义数据，科学数值全部来自源产物。
- `video-ui/dist/index.html`：自包含单文件，内联 CSS、JavaScript 和 JSON。

`story.json` 和 `dist/` 是按需重建的生成物，不提交到 Git。重新生成后可以直接双击 `video-ui/dist/index.html`，不需要开发服务器或网络。

## 检查

```powershell
D:\python\python.exe scripts\build_video_ui.py --check
D:\python\python.exe scripts\check_video_ui.py --browser
D:\python\python.exe -m unittest tests.test_video_ui -v
```

`--check` 会核对生成物是否缺失、过期或被手改。浏览器检查使用 Edge，从 `file://` 加载单文件，验证 8 页路由、deck 挂载和讲稿参数。

## 录屏

1. 打开 `video-ui/dist/index.html`。
2. 建议窗口使用 1920x1080 或 1366x768，按 `F` 进入全屏。
3. 视频开头仍要在终端现场运行：

   ```powershell
   git -C D:\wbworkspace\glyco-analysis rev-parse HEAD
   ```

4. 用左右方向键翻页。需要讲稿时按 `N`，录制正式画面时默认隐藏。
5. 可用 `?slide=3&notes=1` 直接定位第三页并打开讲稿，便于排练和截图。

按键：

- `Right` / `PageDown` / `Space`：下一页
- `Left` / `PageUp`：上一页
- `Home` / `End`：第一页 / 最后一页
- `1` 至 `8`：跳到指定页
- `N`：显示或隐藏讲稿
- `F`：进入或退出全屏

## 页面顺序

1. 封面与完整 Git HEAD
2. W1 可信基线
3. W2 五日路线
4. F1、F2、F3 三条研究线
5. F2 GlycanML Table 3 结果
6. F3 工具轨迹与任务可行性
7. 交付闭环
8. 声明边界与下一周

## 隔离关系

- 不改 `web/` 的源码、数据和构建。
- 不读取网络资源，不加载外部字体、图片或脚本。
- 不写入 `D:\毕设交付`。
- 生成器只读取仓库内已提交的证据文件，`story.json` 记录生成时的完整 HEAD 和每个源文件的 SHA256。
- UI 上的 HEAD 是数据生成基线；视频开头必须另外用终端证明当前仓库 HEAD。
