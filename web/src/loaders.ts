import { projectData } from "./lib";

export async function overviewLoader() {
  return { head_commit: projectData.head_commit };
}