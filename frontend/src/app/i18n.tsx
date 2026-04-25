import { createContext, PropsWithChildren, useContext, useEffect, useMemo, useState } from "react";

const STORAGE_KEY = "fusionagent.ui.locale";

export const locales = ["zh-CN", "en-US"] as const;
export type Locale = (typeof locales)[number];

const dictionaries = {
  "zh-CN": {
    language: {
      label: "界面语言",
      chinese: "中文",
      english: "English",
    },
    shell: {
      navigationLabel: "主导航",
      brandKicker: "FusionAgent",
      brandTitle: "产品界面",
      chips: {
        runtime: "本地运行时",
        graphAware: "图谱感知",
      },
      nav: {
        overview: { label: "总览", meta: "运行态地图册" },
        newRun: { label: "新建运行", meta: "组织输入条件" },
        runs: { label: "运行记录", meta: "追踪证据链" },
        scenarios: { label: "场景空间", meta: "审阅报告" },
        kg: { label: "知识图谱", meta: "查看图谱层" },
        guide: { label: "使用教程", meta: "快速上手路径" },
        settings: { label: "模型设置", meta: "调整运行时" },
      },
    },
    home: {
      eyebrow: "FusionAgent 产品界面",
      title: "运行总图",
      status: "FastAPI 合同已就绪",
      readinessAria: "界面就绪度",
      metrics: {
        apiBoundary: { label: "API 边界", value: "稳定" },
        graphPayloads: { label: "图谱载荷", value: "可用" },
        settingsFlow: { label: "设置流程", value: "已验证" },
      },
      immediateSurfaces: {
        label: "当前能力面",
        marker: "任务 6",
        cards: {
          createRun: { label: "创建运行", value: "上传或任务驱动" },
          runRegistry: { label: "运行注册表", value: "检查与对比通道" },
          scenarios: { label: "场景工作区", value: "报告与 Markdown 实时查看" },
          guide: { label: "使用教程", value: "从设置到图谱的上手流程" },
        },
      },
      readinessLedger: {
        label: "就绪台账",
        marker: "后端已合并",
        items: {
          kgOverview: "图谱总览",
          runGraph: "运行路径图",
          previewMap: "预览地图",
          llmSettings: "模型设置",
        },
      },
    },
    runs: {
      meta: {
        jobTypes: {
          building: "建筑物",
          road: "道路",
          water: "水体",
          poi: "兴趣点",
        },
        inputStrategies: {
          uploaded: "上传数据",
          task_driven_auto: "任务驱动自动采集",
        },
        triggerTypes: {
          user_query: "用户查询",
          disaster_event: "灾害事件",
          scheduled: "定时触发",
        },
        phases: {
          queued: "排队中",
          planning: "规划中",
          validating: "校验中",
          running: "运行中",
          healing: "修复中",
          succeeded: "已成功",
          failed: "已失败",
        },
      },
      create: {
        eyebrow: "运行创建",
        title: "创建运行",
        status: "提交接口已就绪",
        coreRequest: "核心请求",
        spatialContext: "空间上下文",
        submissionRoute: "POST /api/v2/runs",
        labels: {
          jobType: "任务类型",
          inputStrategy: "输入策略",
          triggerType: "触发类型",
          triggerContent: "触发内容",
          disasterType: "灾害类型",
          targetCrs: "目标 CRS",
          debug: "启用调试模式",
          spatialExtent: "空间范围",
          temporalStart: "开始时间",
          temporalEnd: "结束时间",
          osmZip: "OSM ZIP",
          refZip: "参考 ZIP",
        },
        defaults: {
          triggerContent: "手动触发",
        },
        taskDriven: {
          title: "当前为任务驱动采集模式。",
          description: "这一模式下不需要上传制品压缩包。",
        },
        statusCopy: {
          redirecting: "运行已创建，正在跳转到详情页……",
          submitting: "提交中……",
          submit: "启动运行",
        },
      },
      list: {
        eyebrow: "运行注册表",
        title: "运行记录",
        recordsInScope: (count: number) => `当前范围 ${count} 条记录`,
        filters: "筛选条件",
        registry: "注册表",
        compareLane: "对比通道",
        sideBySide: "并排对照",
        labels: {
          phase: "阶段",
          jobType: "任务类型",
          leftRunId: "左侧运行 ID",
          rightRunId: "右侧运行 ID",
        },
        placeholders: {
          phase: "例如 succeeded",
        },
        actions: {
          compareRuns: "比较运行",
        },
        recentRuns: "最近运行",
        loading: "正在加载已落盘的运行记录……",
        error: "加载运行记录失败。",
        empty: "当前筛选条件下没有匹配的运行记录。",
        persistedRun: "已落盘运行",
        all: "全部",
      },
      detail: {
        eyebrow: "运行检查",
        fallbackTitle: "运行详情",
        noJobLoaded: "尚未加载任务类型",
        runSummary: "运行摘要",
        selectRun: "请选择一个已落盘运行。",
        noSnapshot: "尚未加载运行快照。",
        artifactPreview: "结果预览",
        featuresSuffix: " 个要素",
        totalFeatures: (count: number) => `总计 ${count} 个要素`,
        bboxPending: "范围框待生成",
        openGeojson: "打开 GeoJSON 预览",
        previewNotReady: "当前运行的预览路由尚未就绪。",
        previewPending: "运行成功后将在此处显示结果预览。",
        evidenceSnapshot: "证据快照",
        artifactReady: "制品已就绪",
        artifactPending: "制品待生成",
        noDownloadPath: "当前没有可用的下载路径。",
        workflowPlan: "工作流计划",
        unassigned: "未分配",
        loadingPlan: "正在加载计划与检查载荷……",
        loadPlanFailed: "加载检查载荷失败。",
        planUnavailable: "工作流计划暂不可用。",
        stepLabel: (step: number, algorithmId: string) => `步骤 ${step} · ${algorithmId}`,
        auditTimeline: "审计时间线",
        entriesSuffix: " 条",
        auditPending: "运行推进后会在此处显示审计时间线。",
      },
      compare: {
        eyebrow: "运行对比",
        title: "比较运行",
        status: "决策差异",
        comparePair: "对比对",
        labels: {
          leftRunId: "左侧运行 ID",
          rightRunId: "右侧运行 ID",
        },
        actions: {
          loadComparison: "加载对比",
        },
        panels: {
          left: "左侧检查",
          right: "右侧检查",
          awaiting: "等待选择运行",
          noRun: "尚未选择运行",
          providePair: "请输入一对运行 ID 以开始比较。",
          jobType: "任务类型",
          workflow: "工作流",
          auditEvents: "审计事件",
        },
        differingDecisions: "差异决策",
        loading: "正在加载对比载荷……",
        error: "比较所选运行失败。",
        empty: "这一对运行没有报告差异决策。",
      },
    },
    scenarioPage: {
      eyebrow: "场景工作区",
      title: "场景",
      status: (count: number) => `当前 ${count} 个场景`,
      defaults: {
        scenarioName: "场景演练",
        triggerContent: "描述需要覆盖的区域、目标对象和输出要求",
      },
      form: {
        label: "场景提交",
        marker: "POST /api/v2/scenario-runs",
        labels: {
          scenarioName: "场景名称",
          triggerContent: "触发内容",
          disasterType: "灾害类型",
          targetCrs: "目标 CRS",
          jobTypes: "任务类型",
          debug: "启用调试模式",
        },
        actions: {
          submit: "创建场景",
          submitting: "创建中……",
        },
      },
      recent: {
        label: "最近场景",
        marker: "注册表",
        empty: "当前还没有已落盘的场景任务。",
        loading: "正在加载场景列表……",
        error: "加载场景列表失败。",
      },
      reports: {
        label: "报告文档",
        marker: "Markdown",
        empty: "当前场景还没有可读取的报告文档。",
        loadingList: "正在加载文档索引……",
        loadingContent: "正在加载文档内容……",
        error: "加载报告文档失败。",
        tabs: {
          zh: "中文报告",
          en: "English Report",
        },
      },
    },
    kgPage: {
      overview: {
        eyebrow: "知识图谱",
        title: "知识图谱总览",
        status: (count: number) => `当前 ${count} 个节点`,
        graphLabel: "全局图谱",
        graphMarker: "overview",
        loading: "正在加载图谱总览……",
        error: "加载图谱总览失败。",
      },
      runPath: {
        eyebrow: "运行路径图",
        title: "推理路径图",
        status: "单次运行",
        graphLabel: "运行路径",
        graphMarker: "run-path",
        loading: "正在加载运行路径图……",
        error: "加载运行路径图失败。",
        groundingLabel: "落地报告",
        selectedPattern: "命中模式",
        groundedSteps: "落地步骤",
        totalSteps: "总步骤数",
      },
      legend: {
        workflowPattern: "工作流模式",
        algorithm: "算法",
        dataSource: "数据源",
        task: "任务节点",
        relation: "关系",
      },
      view: {
        empty: "当前没有可绘制的图谱节点。",
        loading: "图谱布局计算中……",
        error: "图谱画布加载失败。",
        canvasLabel: "知识图谱画布",
        zoomOut: "缩小图谱",
        fitView: "适配视图",
        zoomIn: "放大图谱",
        zoomLevel: (value: number) => `缩放 ${value}%`,
        interactionHint: "拖动画布查看上下游关系，滚轮可平滑缩放，必要时使用“适配视图”重置布局。",
      },
    },
    guidePage: {
      eyebrow: "控制面教程",
      title: "使用教程",
      status: "从配置到验证的标准路径",
      quickStart: {
        label: "开场检查",
        marker: "4 步",
        steps: [
          {
            title: "确认模型设置",
            description: "先检查 provider、模型名称和超时设置，避免运行创建后才发现运行时不可用。",
          },
          {
            title: "执行一条运行",
            description: "优先从“新建运行”发起一条 building 或 road 任务，用最小输入验证接口和证据链。",
          },
          {
            title: "审阅证据",
            description: "在运行详情里检查计划、审计时间线、预览地图和制品状态，确认输出链路完整。",
          },
          {
            title: "查看图谱",
            description: "打开知识图谱总览或运行路径图，核对模式、算法和数据源是否与预期一致。",
          },
        ],
      },
      surfaces: {
        label: "页面入口",
        marker: "操作地图",
        items: [
          { title: "模型设置", description: "读写 LLM 配置并做连通性校验。" },
          { title: "新建运行", description: "提交 uploaded 或 task-driven_auto 请求。" },
          { title: "运行记录", description: "筛选已落盘运行并进入详情或对比。" },
          { title: "场景空间", description: "查看双语 Markdown 报告和场景级文档。" },
          { title: "知识图谱", description: "检查全局图谱总览和单次运行路径图。" },
        ],
      },
      graphTips: {
        label: "图谱操作提示",
        marker: "交互",
        items: [
          "拖动画布平移视角，滚轮做平滑缩放。",
          "使用图谱工具栏的加减按钮做细粒度缩放。",
          "当视角偏离较远时，用“适配视图”回到整体布局。",
        ],
      },
      actions: {
        settings: "前往模型设置",
        newRun: "打开新建运行",
        knowledgeGraph: "查看知识图谱",
      },
    },
    settingsPage: {
      eyebrow: "运行时设置",
      title: "模型设置",
      status: "读取与应用当前运行时",
      form: {
        label: "LLM 连接",
        marker: "/api/v2/settings/llm",
        labels: {
          provider: "提供方",
          baseUrl: "基础地址",
          apiKey: "API 密钥",
          model: "模型名称",
          timeout: "超时时间（秒）",
        },
        helper: {
          masked: (value: string) => `当前已保存密钥：${value}`,
          empty: "当前未保存 API 密钥。",
        },
        actions: {
          validate: "校验连接",
          validating: "校验中……",
          save: "保存并应用",
          saving: "保存中……",
        },
      },
      state: {
        loading: "正在加载模型设置……",
        loadError: "加载模型设置失败。",
        validateSuccess: "校验通过，可以保存当前配置。",
        saveSuccess: "设置已保存，后续运行会使用新配置。",
      },
      providers: {
        auto: "自动",
        mock: "模拟",
        openai: "OpenAI 兼容",
      },
    },
    map: {
      loading: "正在加载 GeoJSON 预览……",
      error: "地图预览加载失败。",
      empty: "当前没有可展示的 GeoJSON 预览。",
      stats: {
        features: (count: number) => `${count} 个要素`,
        crs: (value: string | null | undefined) => value ? `坐标系 ${value}` : "坐标系待确认",
      },
    },
    placeholders: {
      scenarios: {
        eyebrow: "场景工作区",
        title: "场景",
        status: "文档面板等待 Markdown 绑定",
        states: [
          { label: "提交路由", value: "已就绪" },
          { label: "文档列表", value: "已就绪" },
          { label: "双语报告", value: "待补标签页" },
        ],
        actions: [
          { href: "/runs", label: "查看最近运行" },
          { href: "/settings/llm", label: "调整模型运行时" },
        ],
      },
      kg: {
        eyebrow: "知识图谱",
        title: "知识图谱",
        status: "图谱画布等待 Cytoscape 层接入",
        states: [
          { label: "总览载荷", value: "已就绪" },
          { label: "运行路径载荷", value: "已就绪" },
          { label: "图例与筛选", value: "待补 UI" },
        ],
        actions: [
          { href: "/runs", label: "选择一个运行" },
          { href: "/settings/llm", label: "检查模型设置" },
        ],
      },
      settings: {
        eyebrow: "运行时设置",
        title: "模型设置",
        status: "掩码与校验流程等待表单接入",
        states: [
          { label: "读取掩码密钥", value: "已就绪" },
          { label: "验证连接", value: "已就绪" },
          { label: "保存并刷新", value: "已就绪" },
        ],
        actions: [
          { href: "/runs/new", label: "创建运行" },
          { href: "/kg", label: "打开图谱总览" },
        ],
      },
    },
    routeSurface: {
      shortcuts: (title: string) => `${title} 快捷操作`,
    },
  },
  "en-US": {
    language: {
      label: "Interface language",
      chinese: "中文",
      english: "English",
    },
    shell: {
      navigationLabel: "Primary navigation",
      brandKicker: "FusionAgent",
      brandTitle: "Product Surface",
      chips: {
        runtime: "Local runtime",
        graphAware: "Graph-aware",
      },
      nav: {
        overview: { label: "Overview", meta: "Runtime atlas" },
        newRun: { label: "New Run", meta: "Compose inputs" },
        runs: { label: "Runs", meta: "Track evidence" },
        scenarios: { label: "Scenarios", meta: "Review reports" },
        kg: { label: "Knowledge Graph", meta: "Inspect graph layers" },
        guide: { label: "Guide", meta: "Start with the standard flow" },
        settings: { label: "LLM Settings", meta: "Tune runtime" },
      },
    },
    home: {
      eyebrow: "FusionAgent Product Surface",
      title: "Operational Atlas",
      status: "FastAPI contracts ready",
      readinessAria: "surface readiness",
      metrics: {
        apiBoundary: { label: "API boundary", value: "Stable" },
        graphPayloads: { label: "Graph payloads", value: "Ready" },
        settingsFlow: { label: "Settings flow", value: "Validated" },
      },
      immediateSurfaces: {
        label: "Immediate Surfaces",
        marker: "Task 6",
        cards: {
          createRun: { label: "Create Run", value: "Uploaded or task-driven" },
          runRegistry: { label: "Run Registry", value: "Inspection and compare lanes" },
          scenarios: { label: "Scenario Workspace", value: "Reports and live markdown" },
          guide: { label: "Guide", value: "A guided path from setup to graph review" },
        },
      },
      readinessLedger: {
        label: "Readiness Ledger",
        marker: "Backend merged",
        items: {
          kgOverview: "KG overview",
          runGraph: "Run graph",
          previewMap: "Preview map",
          llmSettings: "LLM settings",
        },
      },
    },
    runs: {
      meta: {
        jobTypes: {
          building: "Building",
          road: "Road",
          water: "Water",
          poi: "POI",
        },
        inputStrategies: {
          uploaded: "Uploaded",
          task_driven_auto: "Task-driven auto",
        },
        triggerTypes: {
          user_query: "User query",
          disaster_event: "Disaster event",
          scheduled: "Scheduled",
        },
        phases: {
          queued: "Queued",
          planning: "Planning",
          validating: "Validating",
          running: "Running",
          healing: "Healing",
          succeeded: "Succeeded",
          failed: "Failed",
        },
      },
      create: {
        eyebrow: "Run Creation",
        title: "Create Run",
        status: "Submission route live",
        coreRequest: "Core Request",
        spatialContext: "Spatial Context",
        submissionRoute: "POST /api/v2/runs",
        labels: {
          jobType: "Job type",
          inputStrategy: "Input strategy",
          triggerType: "Trigger type",
          triggerContent: "Trigger content",
          disasterType: "Disaster type",
          targetCrs: "Target CRS",
          debug: "Enable debug mode",
          spatialExtent: "Spatial extent",
          temporalStart: "Temporal start",
          temporalEnd: "Temporal end",
          osmZip: "OSM ZIP",
          refZip: "Reference ZIP",
        },
        defaults: {
          triggerContent: "manual trigger",
        },
        taskDriven: {
          title: "Task-driven acquisition is active.",
          description: "Uploaded artifact bundles are not required in this mode.",
        },
        statusCopy: {
          redirecting: "Run created. Redirecting to detail view...",
          submitting: "Submitting...",
          submit: "Start run",
        },
      },
      list: {
        eyebrow: "Run Registry",
        title: "Runs",
        recordsInScope: (count: number) => `${count} records in scope`,
        filters: "Filters",
        registry: "Registry",
        compareLane: "Compare Lane",
        sideBySide: "Side by side",
        labels: {
          phase: "Phase",
          jobType: "Job type",
          leftRunId: "Left run ID",
          rightRunId: "Right run ID",
        },
        placeholders: {
          phase: "for example succeeded",
        },
        actions: {
          compareRuns: "Compare runs",
        },
        recentRuns: "Recent Runs",
        loading: "Loading persisted runs...",
        error: "Failed to load runs.",
        empty: "No persisted runs match the current filters.",
        persistedRun: "persisted run",
        all: "all",
      },
      detail: {
        eyebrow: "Run Inspection",
        fallbackTitle: "Run Detail",
        noJobLoaded: "No job loaded",
        runSummary: "Run Summary",
        selectRun: "Select a persisted run.",
        noSnapshot: "No runtime snapshot loaded yet.",
        artifactPreview: "Artifact Preview",
        featuresSuffix: " features",
        totalFeatures: (count: number) => `${count} total features`,
        bboxPending: "BBox pending",
        openGeojson: "Open GeoJSON preview",
        previewNotReady: "Preview route is not ready for this run.",
        previewPending: "Artifact preview will load after a successful run.",
        evidenceSnapshot: "Evidence Snapshot",
        artifactReady: "Artifact ready",
        artifactPending: "Artifact pending",
        noDownloadPath: "No download path available yet.",
        workflowPlan: "Workflow Plan",
        unassigned: "unassigned",
        loadingPlan: "Loading plan and inspection payload...",
        loadPlanFailed: "Failed to load inspection payload.",
        planUnavailable: "Workflow plan is not available yet.",
        stepLabel: (step: number, algorithmId: string) => `Step ${step} · ${algorithmId}`,
        auditTimeline: "Audit Timeline",
        entriesSuffix: " entries",
        auditPending: "Audit timeline will populate once the run advances.",
      },
      compare: {
        eyebrow: "Run Comparison",
        title: "Compare Runs",
        status: "Decision deltas",
        comparePair: "Compare Pair",
        labels: {
          leftRunId: "Left run ID",
          rightRunId: "Right run ID",
        },
        actions: {
          loadComparison: "Load comparison",
        },
        panels: {
          left: "Left Inspection",
          right: "Right Inspection",
          awaiting: "Awaiting run",
          noRun: "No run selected",
          providePair: "Provide a run ID pair to compare.",
          jobType: "Job type",
          workflow: "Workflow",
          auditEvents: "Audit events",
        },
        differingDecisions: "Differing Decisions",
        loading: "Loading comparison payload...",
        error: "Failed to compare the selected runs.",
        empty: "No differing decisions were reported for this pair.",
      },
    },
    scenarioPage: {
      eyebrow: "Scenario Workspace",
      title: "Scenarios",
      status: (count: number) => `${count} scenarios in scope`,
      defaults: {
        scenarioName: "Scenario run",
        triggerContent: "Describe the target region, target entities, and output expectations",
      },
      form: {
        label: "Scenario Submission",
        marker: "POST /api/v2/scenario-runs",
        labels: {
          scenarioName: "Scenario name",
          triggerContent: "Trigger content",
          disasterType: "Disaster type",
          targetCrs: "Target CRS",
          jobTypes: "Job types",
          debug: "Enable debug mode",
        },
        actions: {
          submit: "Create scenario",
          submitting: "Creating...",
        },
      },
      recent: {
        label: "Recent Scenarios",
        marker: "Registry",
        empty: "No persisted scenario runs are available yet.",
        loading: "Loading scenario registry...",
        error: "Failed to load scenario registry.",
      },
      reports: {
        label: "Report Documents",
        marker: "Markdown",
        empty: "No readable report documents are available for this scenario yet.",
        loadingList: "Loading document index...",
        loadingContent: "Loading document content...",
        error: "Failed to load report documents.",
        tabs: {
          zh: "中文报告",
          en: "English Report",
        },
      },
    },
    kgPage: {
      overview: {
        eyebrow: "Knowledge Graph",
        title: "Knowledge Graph Overview",
        status: (count: number) => `${count} nodes in scope`,
        graphLabel: "Global graph",
        graphMarker: "overview",
        loading: "Loading knowledge graph overview...",
        error: "Failed to load the knowledge graph overview.",
      },
      runPath: {
        eyebrow: "Run Path Graph",
        title: "Inference Path Graph",
        status: "Single run",
        graphLabel: "Run path",
        graphMarker: "run-path",
        loading: "Loading run path graph...",
        error: "Failed to load the run path graph.",
        groundingLabel: "Grounding report",
        selectedPattern: "Selected pattern",
        groundedSteps: "Grounded steps",
        totalSteps: "Total steps",
      },
      legend: {
        workflowPattern: "Workflow pattern",
        algorithm: "Algorithm",
        dataSource: "Data source",
        task: "Task node",
        relation: "Relationship",
      },
      view: {
        empty: "No graph nodes are available yet.",
        loading: "Computing graph layout...",
        error: "Failed to load graph canvas.",
        canvasLabel: "Knowledge graph canvas",
        zoomOut: "Zoom out graph",
        fitView: "Fit view",
        zoomIn: "Zoom in graph",
        zoomLevel: (value: number) => `Zoom ${value}%`,
        interactionHint: "Drag to inspect upstream and downstream links, use the wheel for smooth zoom, and fit the view when you need to reset the canvas.",
      },
    },
    guidePage: {
      eyebrow: "Control Plane Guide",
      title: "Guide",
      status: "The standard path from configuration to validation",
      quickStart: {
        label: "Starting checklist",
        marker: "4 steps",
        steps: [
          {
            title: "Check LLM settings",
            description: "Verify the provider, model, and timeout before you create runs, so the runtime is ready when requests arrive.",
          },
          {
            title: "Execute one run",
            description: "Start with a single building or road request from New Run to validate the API surface and evidence chain with minimal input.",
          },
          {
            title: "Review evidence",
            description: "Inspect the plan, audit timeline, preview map, and artifact status in Run Detail to confirm the output path is complete.",
          },
          {
            title: "Inspect the graph",
            description: "Open the global KG overview or a run path graph to verify the selected pattern, algorithms, and data sources.",
          },
        ],
      },
      surfaces: {
        label: "Surface map",
        marker: "Entrypoints",
        items: [
          { title: "LLM Settings", description: "Read and update runtime configuration, then validate connectivity." },
          { title: "New Run", description: "Submit uploaded or task-driven_auto requests." },
          { title: "Runs", description: "Filter persisted runs and jump into detail or compare lanes." },
          { title: "Scenarios", description: "Review bilingual Markdown reports and scenario documents." },
          { title: "Knowledge Graph", description: "Inspect the global graph and per-run path graph." },
        ],
      },
      graphTips: {
        label: "Graph operation tips",
        marker: "Interaction",
        items: [
          "Drag the canvas to pan and use the wheel for smooth zooming.",
          "Use the graph toolbar buttons for finer zoom adjustments.",
          "When the camera drifts too far, use Fit view to recover the full layout.",
        ],
      },
      actions: {
        settings: "Go to LLM Settings",
        newRun: "Open New Run",
        knowledgeGraph: "Open Knowledge Graph",
      },
    },
    settingsPage: {
      eyebrow: "Runtime Settings",
      title: "LLM Settings",
      status: "Read and apply the current runtime",
      form: {
        label: "LLM Connection",
        marker: "/api/v2/settings/llm",
        labels: {
          provider: "Provider",
          baseUrl: "Base URL",
          apiKey: "API Key",
          model: "Model",
          timeout: "Timeout (seconds)",
        },
        helper: {
          masked: (value: string) => `Saved API key: ${value}`,
          empty: "No API key is currently stored.",
        },
        actions: {
          validate: "Validate connection",
          validating: "Validating...",
          save: "Save and apply",
          saving: "Saving...",
        },
      },
      state: {
        loading: "Loading LLM settings...",
        loadError: "Failed to load LLM settings.",
        validateSuccess: "Validation passed. You can save this configuration.",
        saveSuccess: "Settings saved. Future runs will use the new configuration.",
      },
      providers: {
        auto: "Auto",
        mock: "Mock",
        openai: "OpenAI compatible",
      },
    },
    map: {
      loading: "Loading GeoJSON preview...",
      error: "Failed to load map preview.",
      empty: "No GeoJSON preview is available yet.",
      stats: {
        features: (count: number) => `${count} features`,
        crs: (value: string | null | undefined) => value ? `CRS ${value}` : "CRS pending",
      },
    },
    placeholders: {
      scenarios: {
        eyebrow: "Scenario Workspace",
        title: "Scenarios",
        status: "Document panes waiting for markdown binding",
        states: [
          { label: "Submission route", value: "Ready" },
          { label: "Document list", value: "Ready" },
          { label: "Bilingual reports", value: "Pending tabs" },
        ],
        actions: [
          { href: "/runs", label: "Inspect recent runs" },
          { href: "/settings/llm", label: "Adjust model runtime" },
        ],
      },
      kg: {
        eyebrow: "Knowledge Graph",
        title: "Knowledge Graph",
        status: "Graph canvas waiting for Cytoscape layer",
        states: [
          { label: "Overview payload", value: "Ready" },
          { label: "Run path payload", value: "Ready" },
          { label: "Legend and filters", value: "Pending UI" },
        ],
        actions: [
          { href: "/runs", label: "Select a run" },
          { href: "/settings/llm", label: "Check runtime settings" },
        ],
      },
      settings: {
        eyebrow: "Runtime Settings",
        title: "LLM Settings",
        status: "Mask and validation flow ready for form wiring",
        states: [
          { label: "Read masked secret", value: "Ready" },
          { label: "Validate connection", value: "Ready" },
          { label: "Apply and refresh", value: "Ready" },
        ],
        actions: [
          { href: "/runs/new", label: "Create a run" },
          { href: "/kg", label: "Open graph overview" },
        ],
      },
    },
    routeSurface: {
      shortcuts: (title: string) => `${title} shortcuts`,
    },
  },
} as const;

type Dictionary = (typeof dictionaries)["zh-CN"];

type I18nContextValue = {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  copy: Dictionary;
};

const I18nContext = createContext<I18nContextValue | null>(null);

function isLocale(value: string | null): value is Locale {
  return value !== null && (locales as readonly string[]).includes(value);
}

export function I18nProvider({ children }: PropsWithChildren) {
  const [locale, setLocale] = useState<Locale>(() => {
    if (typeof window === "undefined") {
      return "zh-CN";
    }
    const stored = window.localStorage.getItem(STORAGE_KEY);
    return isLocale(stored) ? stored : "zh-CN";
  });

  useEffect(() => {
    if (typeof window !== "undefined") {
      window.localStorage.setItem(STORAGE_KEY, locale);
    }
  }, [locale]);

  const value = useMemo<I18nContextValue>(
    () => ({
      locale,
      setLocale,
      copy: dictionaries[locale] as Dictionary,
    }),
    [locale],
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n() {
  const context = useContext(I18nContext);
  if (context === null) {
    throw new Error("useI18n must be used within I18nProvider.");
  }
  return context;
}
