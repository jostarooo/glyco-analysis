# web 交付界面直接打开验证

日期：2026-11-01

## 失败复现

直接用 Edge 打开 `file:///D:/wbworkspace/glyco-analysis/web/dist/index.html` 时，
`#root` 为空，页面全白。Playwright 捕获到两条 CORS 错误：

```text
Access to script at 'file:///.../assets/index-CBqYTIjM.js' from origin 'null'
has been blocked by CORS policy
Access to CSS stylesheet at 'file:///.../assets/index-KyyqUDJP.css' from origin 'null'
has been blocked by CORS policy
```

根因是原构建输出把 JavaScript 和 CSS 作为外部文件引用。`file://` 页面的源为 `null`，
Chromium 系浏览器不会按跨域规则加载这些模块脚本和样式表，因此 React 没有启动。

## 修复

生产构建接入 `vite-plugin-singlefile 2.3.4`，把 JavaScript 和 CSS 内联进单个
`web/dist/index.html`。修复提交为 `51b421ff8fed929fb273abaec4ce886baa6f680b`。

构建后 `web/dist/` 只有一个文件：

```text
index.html
bytes: 427469
sha256: B6A37F3D943B022C30B117CD687615E07A6491DEAEB98618116EC080FEE3A8B9
```

## 通过证据

`D:\python\python.exe scripts/check_web_dist.py --browser` 输出：

```text
PASS static single-file contract: D:\wbworkspace\glyco-analysis\web\dist\index.html
- bytes: 427469
PASS Edge file:// mount: file:///D:/wbworkspace/glyco-analysis/web/dist/index.html
```

随后用 Edge 和 Playwright 直接加载同一文件并遍历四个 hash 路由：

| 页面 | 标题 | 导航链接 | 控制台错误 | 页面脚本错误 |
|---|---|---:|---:|---:|
| 项目总览 | 项目总览 | 4 | 0 | 0 |
| 核心指标 | 核心指标 | 4 | 0 | 0 |
| 工具与任务 | 工具与任务 | 4 | 0 | 0 |
| 口径与边界 | 口径与边界 | 4 | 0 | 0 |

结构化结果见 `reports/w2_day5/file_open_verification.json`。

## 复现命令

```powershell
D:\node\node.exe D:\node\node_modules\npm\bin\npm-cli.js run build --prefix D:\wbworkspace\glyco-analysis\web
$env:PYTHONUTF8='1'
D:\python\python.exe D:\wbworkspace\glyco-analysis\scripts\check_web_dist.py --browser
```

`scripts/check_web_dist.py` 同时检查外部资源引用为零、内联模块和内联样式存在，
并通过 Edge 的 `file://` 页面确认 `app-shell` 已挂载。行为测试见
`tests/test_web_dist_contract.py`。

最终构建把页头标记从“演示版本”改为“数据基线”。`head_commit` 是生成 web 数据时的
仓库 HEAD，不可能是包含它自身的下一次提交；视频开头仍必须现场运行
`git rev-parse HEAD` 证明交付前最新提交。
