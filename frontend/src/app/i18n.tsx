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
        dashboard: { label: "任务中心", meta: "查看当前运行与下一步" },
        newRun: { label: "新建任务", meta: "组织输入条件并发起运行" },
        runs: { label: "历史任务", meta: "回看任务与关键结果" },
        scenarios: { label: "场景与报告", meta: "审阅报告并回看关联运行" },
        validation: { label: "验证会话", meta: "查看工程验证结果" },
        kg: { label: "知识图谱", meta: "查看图谱与推理路径" },
        guide: { label: "使用指南", meta: "按流程快速上手" },
        settings: { label: "模型设置", meta: "调整运行时与模型连接" },
      },
    },
    home: {
      eyebrow: "FusionAgent 操作工作台",
      title: "任务中心",
      status: (configured: boolean) => (configured ? "当前可直接创建与追踪任务" : "请先完成模型设置后再创建任务"),
      readinessAria: "任务中心概览",
      metrics: {
        runtime: { label: "模型提供方", fallback: "未配置" },
        graph: { label: "图谱后端", fallback: "待确认" },
        attention: {
          label: "待关注项",
          value: (count: number) => `${count} 项`,
        },
      },
      focusRuns: {
        label: "当前关注任务",
        marker: "运行态",
        loading: "正在加载任务中心摘要……",
        error: "加载任务中心摘要失败。",
        emptyTitle: "当前没有需要优先处理的任务。",
        emptyDescription: "你可以直接发起新任务，或转到历史任务查看最近一次运行。",
        noTrigger: "暂无触发内容摘要",
      },
      quickStart: {
        label: "快速入口",
        marker: "主流程",
        cards: {
          newRun: { label: "新建任务", value: "立即发起一条运行任务" },
          history: { label: "历史任务", value: "筛选过往运行并回看详情" },
          reports: { label: "场景与报告", value: "阅读报告并回到关联运行" },
          graph: { label: "知识图谱", value: "查看全局图谱与推理路径" },
        },
      },
      recentOutputs: {
        label: "最近成果",
        marker: "回看与复盘",
        empty: "暂无",
        items: {
          recentRun: "最近任务",
          recentScenario: "最近场景",
          evidenceGaps: "待补证据",
        },
        actions: {
          openRun: "打开最近任务",
          openReports: "查看场景与报告",
        },
      },
      nextSteps: {
        label: "下一步建议",
        marker: "操作链路",
        configured: "当前模型设置已就绪，可直接新建任务并追踪运行状态。",
        unconfigured: "当前尚未配置模型连接，建议先进入模型设置完成 provider、模型与密钥配置。",
        review: "任务创建后，优先在详情页检查结果预览、证据制品与工作流计划。",
        explain: "如需理解系统为何这样规划任务，可继续进入知识图谱和推理路径页面。",
        actions: {
          configure: "前往模型设置",
          createRun: "立即新建任务",
          guide: "查看使用指南",
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
        eyebrow: "任务历史中心",
        title: "历史任务",
        recordsInScope: (count: number) => `当前范围 ${count} 条记录`,
        filters: "筛选条件",
        registry: "注册表",
        compareLane: "任务对比",
        sideBySide: "并排对照",
        quickFilters: "快捷阶段筛选",
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
          compareRuns: "比较任务",
          newTask: "新建任务",
        },
        compareHint: "当你已经知道两条运行 ID 时，可在这里快速进入对比页面。",
        recentRuns: "历史任务列表",
        loading: "正在加载已落盘的运行记录……",
        error: "加载运行记录失败。",
        empty: "当前筛选条件下没有匹配的运行记录。",
        persistedRun: "已落盘运行",
        noTrigger: "暂无触发内容摘要",
        all: "全部",
      },
      detail: {
        eyebrow: "任务详情",
        fallbackTitle: "运行详情",
        noJobLoaded: "尚未加载任务类型",
        runSummary: "运行摘要",
        selectRun: "请选择一个已落盘运行。",
        noSnapshot: "当前没有失败摘要，可继续查看预览、计划与审计信息。",
        artifactPreview: "结果预览",
        featuresSuffix: " 个要素",
        totalFeatures: (count: number) => `总计 ${count} 个要素`,
        bboxPending: "范围框待生成",
        openGeojson: "打开 GeoJSON 预览",
        downloadArtifact: "下载制品",
        previewNotReady: "当前运行的预览路由尚未就绪。",
        previewPending: "运行成功后将在此处显示结果预览。",
        evidenceSnapshot: "证据与结果",
        artifactReady: "制品已就绪",
        artifactPending: "制品待生成",
        noDownloadPath: "当前没有可用的下载路径。",
        workflowPlan: "工作流计划",
        reasoningTrace: "推理链摘要",
        reasoningPending: "当前还没有可展示的推理链摘要。",
        relatedActions: "关联入口",
        relatedMarker: "主链路",
        summaryItems: {
          jobType: "任务类型",
          createdAt: "创建时间",
          updatedAt: "更新时间",
        },
        actions: {
          backToHistory: "返回历史任务",
          compareFromHere: "从这里发起对比",
          openReports: "查看场景与报告",
          openGuide: "查看使用指南",
        },
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
      eyebrow: "场景与报告中心",
      title: "场景与报告",
      status: (count: number) => `当前 ${count} 个场景`,
      defaults: {
        scenarioName: "场景演练",
        triggerContent: "描述需要覆盖的区域、目标对象和输出要求",
      },
      form: {
        label: "新建场景",
        marker: "POST /api/v2/scenario-runs",
        helper: "当你需要生成一组关联运行与报告时，可在这里创建新的场景任务。",
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
        label: "场景列表",
        marker: "注册表",
        empty: "当前还没有已落盘的场景任务。",
        loading: "正在加载场景列表……",
        error: "加载场景列表失败。",
        childRuns: (count: number) => `${count} 个关联运行`,
      },
      overview: {
        label: "场景概览",
        marker: "摘要",
        empty: "请选择一个场景以查看报告与关联运行。",
        noChildRuns: "当前场景还没有可跳转的关联运行。",
        items: {
          scenarioId: "场景 ID",
          phase: "当前阶段",
          reports: "报告数",
        },
        recovery: {
          error: "恢复场景失败。",
          actions: {
            resume: "恢复场景",
            retryFailed: "重试失败任务",
            submitting: "提交中……",
          },
        },
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
    validationPage: {
      eyebrow: "工程验证",
      title: "验证会话",
      status: (count: number) => `当前 ${count} 个验证会话`,
      list: {
        label: "会话列表",
        marker: "validation_summary.json",
        loading: "正在加载验证会话……",
        error: "加载验证会话失败。",
        empty: "当前还没有已落盘的验证会话。",
      },
      summary: {
        label: "会话摘要",
        marker: "最终汇总",
        empty: "请选择一个验证会话查看结果。",
        items: {
          passRate: "通过率",
          passed: "通过用例",
          failed: "失败用例",
          total: "总用例",
          matrix: "矩阵",
          createdAt: "创建时间",
          gitCommit: "Git commit",
          outputRoot: "输出根目录",
        },
      },
      failures: {
        label: "失败用例",
        marker: "failure reasons",
        empty: "当前会话没有失败用例。",
        reasons: "失败原因",
        links: "关联入口",
      },
    },
    kgPage: {
      overview: {
        eyebrow: "知识图谱",
        title: "知识图谱总览",
        status: (count: number) => `当前 ${count} 个节点`,
        summaryLabel: "图谱摘要",
        summaryMarker: "入口说明",
        items: {
          nodes: "节点数",
          edges: "边数",
        },
        hint: "如果你想理解某次任务为何采用特定模式与算法，先从历史任务进入对应详情，再打开单次运行推理路径图。",
        actions: {
          history: "回到历史任务",
        },
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
        hint: "将此页面与任务详情联动查看，可以更快理解系统为何选择当前工作流与数据源。",
        actions: {
          backToRun: "返回任务详情",
          overview: "查看图谱总览",
        },
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
      eyebrow: "流程指南",
      title: "使用指南",
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
            title: "执行一条任务",
            description: "优先从“新建任务”发起一条 building 或 road 任务，用最小输入验证接口和证据链。",
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
      workflowMap: {
        label: "流程地图",
        marker: "按步骤进入",
        items: [
          { title: "1. 模型设置", description: "先完成 provider、模型与密钥配置", href: "/settings/llm" },
          { title: "2. 新建任务", description: "提交一条最小可验证的运行任务", href: "/runs/new" },
          { title: "3. 历史任务", description: "回看当前或过往任务的详情与状态", href: "/runs" },
          { title: "4. 场景与报告", description: "查看报告文档并跳回关联运行", href: "/scenarios" },
          { title: "5. 知识图谱", description: "查看图谱总览与单次运行推理路径", href: "/kg" },
        ],
      },
      surfaces: {
        label: "页面入口",
        marker: "操作地图",
        items: [
          { title: "模型设置", description: "读写 LLM 配置并做连通性校验。" },
          { title: "新建任务", description: "提交 uploaded 或 task-driven_auto 请求。" },
          { title: "历史任务", description: "筛选已落盘运行并进入详情或对比。" },
          { title: "场景与报告", description: "查看双语 Markdown 报告和场景级文档。" },
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
        newRun: "打开新建任务",
        knowledgeGraph: "查看知识图谱",
        reports: "查看场景与报告",
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
        dashboard: { label: "Task Center", meta: "See active runs and the next step" },
        newRun: { label: "New Task", meta: "Compose inputs and launch a run" },
        runs: { label: "Task History", meta: "Review past runs and key outputs" },
        scenarios: { label: "Scenarios & Reports", meta: "Review reports and linked runs" },
        validation: { label: "Validation", meta: "Inspect engineering validation" },
        kg: { label: "Knowledge Graph", meta: "Inspect graph and reasoning paths" },
        guide: { label: "Guide", meta: "Follow the standard workflow" },
        settings: { label: "LLM Settings", meta: "Tune runtime and model connectivity" },
      },
    },
    home: {
      eyebrow: "FusionAgent Operator Workbench",
      title: "Task Center",
      status: (configured: boolean) => (configured ? "Ready to create and track tasks" : "Complete LLM settings before creating tasks"),
      readinessAria: "task center overview",
      metrics: {
        runtime: { label: "LLM provider", fallback: "Not configured" },
        graph: { label: "Graph backend", fallback: "Pending" },
        attention: {
          label: "Items to review",
          value: (count: number) => `${count} item${count === 1 ? "" : "s"}`,
        },
      },
      focusRuns: {
        label: "Runs to Watch",
        marker: "Live status",
        loading: "Loading task center summary...",
        error: "Failed to load task center summary.",
        emptyTitle: "No runs need immediate attention.",
        emptyDescription: "You can launch a new task now, or open task history to inspect the latest run.",
        noTrigger: "No trigger summary available",
      },
      quickStart: {
        label: "Quick actions",
        marker: "Main workflow",
        cards: {
          newRun: { label: "New Task", value: "Launch a new run now" },
          history: { label: "Task History", value: "Filter previous runs and reopen details" },
          reports: { label: "Scenarios & Reports", value: "Read reports and jump back to linked runs" },
          graph: { label: "Knowledge Graph", value: "Inspect the global graph and reasoning path" },
        },
      },
      recentOutputs: {
        label: "Recent outputs",
        marker: "Review and replay",
        empty: "None",
        items: {
          recentRun: "Latest run",
          recentScenario: "Latest scenario",
          evidenceGaps: "Evidence gaps",
        },
        actions: {
          openRun: "Open latest run",
          openReports: "Open scenarios & reports",
        },
      },
      nextSteps: {
        label: "Suggested next step",
        marker: "Workflow",
        configured: "LLM settings are ready, so you can create a task and follow its progress immediately.",
        unconfigured: "LLM connectivity is not configured yet. Start in settings to finish the provider, model, and key setup.",
        review: "After task creation, check the preview, evidence artifact, and workflow plan in the detail page first.",
        explain: "When you need to understand why the system chose a path, continue into the knowledge graph and reasoning view.",
        actions: {
          configure: "Go to LLM Settings",
          createRun: "Create a task now",
          guide: "Open the guide",
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
        eyebrow: "Task History Center",
        title: "Task History",
        recordsInScope: (count: number) => `${count} records in scope`,
        filters: "Filters",
        registry: "Registry",
        compareLane: "Task Compare",
        sideBySide: "Side by side",
        quickFilters: "Quick phase filters",
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
          compareRuns: "Compare tasks",
          newTask: "Create a task",
        },
        compareHint: "When you already know two run IDs, use this lane to jump directly into the comparison page.",
        recentRuns: "Task history list",
        loading: "Loading persisted runs...",
        error: "Failed to load runs.",
        empty: "No persisted runs match the current filters.",
        persistedRun: "persisted run",
        noTrigger: "No trigger summary available",
        all: "all",
      },
      detail: {
        eyebrow: "Task Detail",
        fallbackTitle: "Run Detail",
        noJobLoaded: "No job loaded",
        runSummary: "Run Summary",
        selectRun: "Select a persisted run.",
        noSnapshot: "No failure summary is available yet. Continue with preview, plan, and audit details.",
        artifactPreview: "Artifact Preview",
        featuresSuffix: " features",
        totalFeatures: (count: number) => `${count} total features`,
        bboxPending: "BBox pending",
        openGeojson: "Open GeoJSON preview",
        downloadArtifact: "Download artifact",
        previewNotReady: "Preview route is not ready for this run.",
        previewPending: "Artifact preview will load after a successful run.",
        evidenceSnapshot: "Evidence & Outputs",
        artifactReady: "Artifact ready",
        artifactPending: "Artifact pending",
        noDownloadPath: "No download path available yet.",
        workflowPlan: "Workflow Plan",
        reasoningTrace: "Reasoning Trace",
        reasoningPending: "No reasoning summary is available yet.",
        relatedActions: "Linked Actions",
        relatedMarker: "Main workflow",
        summaryItems: {
          jobType: "Job type",
          createdAt: "Created at",
          updatedAt: "Updated at",
        },
        actions: {
          backToHistory: "Back to task history",
          compareFromHere: "Start compare from here",
          openReports: "Open scenarios & reports",
          openGuide: "Open the guide",
        },
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
      eyebrow: "Scenarios & Reports Center",
      title: "Scenarios & Reports",
      status: (count: number) => `${count} scenarios in scope`,
      defaults: {
        scenarioName: "Scenario run",
        triggerContent: "Describe the target region, target entities, and output expectations",
      },
      form: {
        label: "Create Scenario",
        marker: "POST /api/v2/scenario-runs",
        helper: "Use this form when you need one scenario to generate a linked set of runs and reports.",
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
        label: "Scenario list",
        marker: "Registry",
        empty: "No persisted scenario runs are available yet.",
        loading: "Loading scenario registry...",
        error: "Failed to load scenario registry.",
        childRuns: (count: number) => `${count} linked run${count === 1 ? "" : "s"}`,
      },
      overview: {
        label: "Scenario overview",
        marker: "Summary",
        empty: "Select a scenario to inspect reports and linked runs.",
        noChildRuns: "No linked runs are available for this scenario yet.",
        items: {
          scenarioId: "Scenario ID",
          phase: "Current phase",
          reports: "Report count",
        },
        recovery: {
          error: "Failed to resume the scenario.",
          actions: {
            resume: "Resume scenario",
            retryFailed: "Retry failed tasks",
            submitting: "Submitting...",
          },
        },
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
    validationPage: {
      eyebrow: "Engineering Validation",
      title: "Validation Sessions",
      status: (count: number) => `${count} validation session${count === 1 ? "" : "s"} in scope`,
      list: {
        label: "Session list",
        marker: "validation_summary.json",
        loading: "Loading validation sessions...",
        error: "Failed to load validation sessions.",
        empty: "No persisted validation sessions are available yet.",
      },
      summary: {
        label: "Session summary",
        marker: "Final summary",
        empty: "Select a validation session to inspect results.",
        items: {
          passRate: "Pass rate",
          passed: "Passed cases",
          failed: "Failed cases",
          total: "Total cases",
          matrix: "Matrix",
          createdAt: "Created at",
          gitCommit: "Git commit",
          outputRoot: "Output root",
        },
      },
      failures: {
        label: "Failed cases",
        marker: "failure reasons",
        empty: "No failed cases were reported for this session.",
        reasons: "Failure reasons",
        links: "Linked entries",
      },
    },
    kgPage: {
      overview: {
        eyebrow: "Knowledge Graph",
        title: "Knowledge Graph Overview",
        status: (count: number) => `${count} nodes in scope`,
        summaryLabel: "Graph summary",
        summaryMarker: "Entry guidance",
        items: {
          nodes: "Node count",
          edges: "Edge count",
        },
        hint: "If you want to understand why a task picked a pattern or algorithm, start from task history, open the run detail, then jump into the per-run reasoning graph.",
        actions: {
          history: "Back to task history",
        },
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
        hint: "Use this page together with the task detail page to understand why the system chose the current workflow and data sources.",
        actions: {
          backToRun: "Back to task detail",
          overview: "Open graph overview",
        },
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
      workflowMap: {
        label: "Workflow map",
        marker: "Follow the chain",
        items: [
          { title: "1. LLM Settings", description: "Finish the provider, model, and key setup first", href: "/settings/llm" },
          { title: "2. New Task", description: "Submit one minimal run you can validate quickly", href: "/runs/new" },
          { title: "3. Task History", description: "Reopen the current or previous runs and inspect details", href: "/runs" },
          { title: "4. Scenarios & Reports", description: "Read report documents and jump back to linked runs", href: "/scenarios" },
          { title: "5. Knowledge Graph", description: "Inspect the overview graph and per-run reasoning path", href: "/kg" },
        ],
      },
      surfaces: {
        label: "Surface map",
        marker: "Entrypoints",
        items: [
          { title: "LLM Settings", description: "Read and update runtime configuration, then validate connectivity." },
          { title: "New Task", description: "Submit uploaded or task-driven_auto requests." },
          { title: "Task History", description: "Filter persisted runs and jump into detail or compare lanes." },
          { title: "Scenarios & Reports", description: "Review bilingual Markdown reports and scenario documents." },
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
        newRun: "Open New Task",
        knowledgeGraph: "Open Knowledge Graph",
        reports: "Open scenarios & reports",
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
