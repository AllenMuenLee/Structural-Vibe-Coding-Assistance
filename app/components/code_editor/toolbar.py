from PyQt6.QtWidgets import QWidget, QHBoxLayout, QPushButton


def build_toolbar(
    *,
    root,
    flowchart_data,
    on_back_to_canvas,
    on_run_project,
    open_terminal_fn,
):
    toolbar = QWidget()
    toolbar.setObjectName("Toolbar")
    toolbar_layout = QHBoxLayout(toolbar)
    toolbar_layout.setContentsMargins(10, 8, 10, 8)
    toolbar_layout.setSpacing(8)

    refine_btn = QPushButton("Back")
    refine_btn.setObjectName("ToolbarButton")
    refine_btn.setToolTip("Back to flowchart")
    refine_btn.clicked.connect(lambda: on_back_to_canvas() if on_back_to_canvas else None)

    open_terminal_btn = QPushButton("Terminal")
    open_terminal_btn.setObjectName("ToolbarButton")
    open_terminal_btn.setToolTip("Open system terminal in project folder")
    open_terminal_btn.clicked.connect(
        lambda: open_terminal_fn(
            flowchart_data.get("project_root", "") if flowchart_data else ""
        )
    )

    run_btn = QPushButton("Run")
    run_btn.setObjectName("PrimaryButton")
    run_btn.setToolTip("Run project")
    run_btn.clicked.connect(on_run_project)


    toolbar_layout.addWidget(refine_btn)
    toolbar_layout.addWidget(open_terminal_btn)
    toolbar_layout.addStretch()
    toolbar_layout.addWidget(run_btn)
    return toolbar, None
