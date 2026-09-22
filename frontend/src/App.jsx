import React, { useCallback, useEffect, useState } from "react";
import { api } from "./api.js";
import ProjectList from "./components/ProjectList.jsx";
import Editor from "./components/Editor.jsx";
import MergeView from "./components/MergeView.jsx";

export default function App() {
  const [projects, setProjects] = useState([]);
  const [project, setProject] = useState(null);
  const [view, setView] = useState("list"); // list | editor | merge
  const [toast, setToast] = useState(null);

  const notify = useCallback((message, isError = false) => {
    setToast({ message, isError });
    setTimeout(() => setToast(null), 3200);
  }, []);

  const refreshProjects = useCallback(async () => {
    setProjects(await api.listProjects());
  }, []);

  const loadProject = useCallback(async (pid) => {
    setProject(await api.getProject(pid));
  }, []);

  const openProject = useCallback(async (pid) => {
    await loadProject(pid);
    setView("editor");
  }, [loadProject]);

  useEffect(() => {
    refreshProjects().catch((e) => notify(e.message, true));
  }, [refreshProjects, notify]);

  const backToList = async () => {
    setProject(null);
    setView("list");
    await refreshProjects();
  };

  return (
    <div>
      <div className="topbar">
        <span className="brand" onClick={backToList}>访谈音频校注</span>
        {project && (
          <span className="crumb">
            / {project.name}
            {view === "merge" ? " / 三方合并" : ""}
          </span>
        )}
      </div>

      <div className="container">
        {view === "list" && (
          <ProjectList
            projects={projects}
            onRefresh={refreshProjects}
            onOpen={openProject}
            notify={notify}
          />
        )}
        {view === "editor" && project && (
          <Editor
            project={project}
            onReload={() => loadProject(project.id)}
            onBack={backToList}
            onOpenMerge={() => setView("merge")}
            notify={notify}
          />
        )}
        {view === "merge" && project && (
          <MergeView
            project={project}
            onBack={() => setView("editor")}
            onOpenProject={openProject}
            notify={notify}
          />
        )}
      </div>

      {toast && (
        <div
          style={{
            position: "fixed", bottom: 24, left: "50%", transform: "translateX(-50%)",
            background: toast.isError ? "#7f1d1d" : "#10243e", color: "#fff",
            padding: "8px 18px", borderRadius: 8, fontSize: 13, zIndex: 100,
            boxShadow: "0 4px 16px rgba(0,0,0,.2)",
          }}
        >
          {toast.message}
        </div>
      )}
    </div>
  );
}
