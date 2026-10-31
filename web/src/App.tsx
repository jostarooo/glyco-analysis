import { Outlet, NavLink, useRouteLoaderData } from "react-router-dom";
import { projectData, shortCommit } from "./lib";

export default function App() {
  const loader = useRouteLoaderData("root") as Awaited<ReturnType<typeof import("./loaders").overviewLoader>>;
  const head = loader?.head_commit ?? projectData.head_commit;
  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="topbar-inner">
          <div className="brand">
            <strong>糖基化分析系统</strong>
            <span>F1 位点预测 · F2 糖链模型 · F3 工具调用智能体</span>
          </div>
          <span className="head-commit">演示版本 <code>{shortCommit(head)}</code></span>
          <nav className="nav">
            <NavLink to="/" end>项目总览</NavLink>
            <NavLink to="/metrics">核心指标</NavLink>
            <NavLink to="/tools">工具与任务</NavLink>
            <NavLink to="/boundaries">口径与边界</NavLink>
          </nav>
        </div>
      </header>
      <main><Outlet /></main>
      <footer>
        <div className="footer-inner">
          <span>数据由 scripts/build_web_data.py 从仓库真实产物生成，界面不含写死指标。</span>
          <span className="hash">schema {projectData.schema_version}</span>
        </div>
      </footer>
    </div>
  );
}