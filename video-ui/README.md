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

`--check` 会核对生成物是否缺失、过期或被手改。浏览器检查使用 Edge，从 `file://` 加载单文件，验证 9 页路由、deck 挂载、讲稿参数，以及 F1、F2、F3 三个现场交互在两个分辨率下可用。

## 录屏

1. 打开 `video-ui/dist/index.html`。
2. 建议窗口使用 1920x1080 或 1366x768，按 `F` 进入全屏。
3. 视频开头仍要在终端现场运行：

   ```powershell
   git -C D:\wbworkspace\glyco-analysis rev-parse HEAD
   ```

4. 用左右方向键翻页。需要讲稿时按 `N`，录制正式画面时默认隐藏。
5. 可用 `?slide=6&notes=1` 直接定位 F2 页并打开讲稿，便于排练和截图。

## 三项功能演示

### F1 位点工作台

1. 从 201 个真实候选中选择题号，或点击四个快速预设。
2. 对照 UniProt、Sequon、35M 和 150M 四列判断。
3. 在输入框填入 `NST` 并点击运行，页面会现场执行 `N-X-S/T`、X 不能为 `P` 的序列规则。
4. 再填入 `NPS`，展示 P 被规则排除。输入框获得焦点时，数字键不会误触翻页。

### F2 结果检查器

1. 在免疫原性和糖基化连接两个任务间切换。
2. 点击 seed 0、1、2，查看对应种子的真实 test、validation 和 best epoch。
3. 页面同时显示三种子均值、标准差和论文 Table 3 参照差。
4. 页面没有伪造混淆矩阵，只显示源 JSON 中真实存在的字段。

### F3 轨迹播放器

1. 从 50 道真实任务中选择题号，或按“完整轨迹”“含工具失败”“无最终回答”筛选。
2. 点击“下一步”逐条播放真实工具调用，观察工具名、参数、状态和错误。
3. 点击“显示全部”查看最终回答是否存在及原文。
4. 右侧五项数字是轨迹或输出存在性指标，不是答案正确率。

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
3. F1 位点工作台
4. W2 五日路线
5. F1、F2、F3 三条研究线
6. F2 结果检查器
7. F3 轨迹播放器
8. 交付闭环
9. 声明边界与下一周

## 隔离关系

- 不改 `web/` 的源码、数据和构建。
- 不读取网络资源，不加载外部字体、图片或脚本。
- 不写入正式 `D:\毕设交付\W02_2026-11-03` 周交付目录。录制辅助副本单独放在 `D:\毕设交付\_视频录制辅助`。
- 生成器只读取仓库内已提交的证据文件，`story.json` 记录生成时的完整 HEAD 和每个源文件的 SHA256。
- UI 上的 HEAD 是数据生成基线；视频开头必须另外用终端证明当前仓库 HEAD。
