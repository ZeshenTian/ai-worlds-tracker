"use client";

import { useEffect, useSyncExternalStore } from "react";

export type Lang = "zh" | "en";

const STORAGE_KEY = "atlas-lang";
const EVENT_NAME = "atlas:lang";

function readClientLang(): Lang {
  if (typeof window === "undefined") return "en";
  try {
    return window.localStorage.getItem(STORAGE_KEY) === "zh" ? "zh" : "en";
  } catch {
    return "en";
  }
}

function subscribe(callback: () => void) {
  if (typeof window === "undefined") return () => {};
  const onStorage = (e: StorageEvent) => {
    if (!e.key || e.key === STORAGE_KEY) callback();
  };
  window.addEventListener(EVENT_NAME, callback);
  window.addEventListener("storage", onStorage);
  return () => {
    window.removeEventListener(EVENT_NAME, callback);
    window.removeEventListener("storage", onStorage);
  };
}

export function setLang(next: Lang) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, next);
  } catch {
    /* ignore storage restrictions */
  }
  document.documentElement.lang = next === "en" ? "en" : "zh-CN";
  window.dispatchEvent(new Event(EVENT_NAME));
}

export function useLang(): [Lang, () => void] {
  const lang = useSyncExternalStore<Lang>(subscribe, readClientLang, () => "en");

  useEffect(() => {
    document.documentElement.lang = lang === "en" ? "en" : "zh-CN";
  }, [lang]);

  const toggle = () => setLang(lang === "zh" ? "en" : "zh");
  return [lang, toggle];
}

export const copy = {
  zh: {
    eraScope:"模型范围", frontierOnly:"仅前沿模型", includeArchive:"全部（含归档）",
    modes: { playable: "可试玩", video: "视频演示", all: "全部" },
    brand: "WorldFeed 探索",
    navCatalog: "目录",
    navTrends: "趋势",
    submit: "提交",
    skipLink: "跳到正文",
    searchPlaceholder: "搜索案例、模型、技术栈…",
    searchModalPlaceholder: "搜索案例名、模型（Claude / GPT / Gemini）或技术栈…",
    searchClear: "清空搜索",
    searchOpen: "快捷搜索",
    searchClose: "关闭",
    searchFilterCta: (q: string) => `在目录中筛选 “${q}”`,
    searchEmpty: (q: string) => `未找到 “${q}”`,
    searchHints: "↑↓ 选择 · Enter 打开 · Esc 关闭",
    totalCount: (n: number) => `${n} 个世界`,
    // Facets & KPIs
    filter: "筛选",
    filterClose: "关闭筛选",
    facetModels: "模型",
    allModels: "全部模型",
    playable: "可试玩",
    openSource: "开源",
    hasWorkflow: "含工作流",
    withPreview: "有封面图",
    facetThemes: "主题",
    facetMore: "技术栈与月份",
    techStack: "技术栈",
    publishMonth: "月份",
    all: "全部",
    sortFeatured: "精选",
    sortRecent: "最新",
    sortIngested: "最近收录",
    sortTitle: "名称",
    viewGrid: "卡片",
    viewList: "列表",
    viewTable: "表格",
    clearAll: "清除",
    openInspector: "预览",
    closeInspector: "收起预览",
    inspectorTitle: "详情",
    fullPage: "完整页",
    // Actions
    play: "试玩",
    visit: "访问",
    openDemo: "打开试玩",
    visitDemo: "访问项目",
    sourceCode: "源码",
    viewCode: "查看源码",
    originalPost: "原帖",
    originalPage: "原文",
    viewSource: "溯源",
    // Cards / Inspector / Detail
    workflow: "工作流",
    workflowSteps: (n: number) => `${n} 步`,
    toolsAndPrompts: "工具与提示",
    evidence: "原文证据",
    facts: "信息",
    model: "模型",
    reproducibility: "复现",
    license: "开源",
    openYes: "开源",
    openNo: "闭源",
    timeLabel: "耗时",
    costLabel: "费用",
    minutes: (n: number) => `${n} 分钟`,
    backToCatalog: "返回目录",
    similarTitle: "同主题",
    author: "作者",
    // Empty & Pagination
    emptyTitle: "没有匹配的案例",
    emptyHint: "试试更短的关键词或清除筛选。",
    loadMore: "加载更多",
    showAll: (n: number) => `全部 (${n})`,
    // Table headers
    colWorld: "案例",
    colModel: "模型",
    colTheme: "主题",
    colStack: "技术栈",
    colActions: "入口",
    colCost: "费用 (USD)",
    colTime: "耗时 (分钟)",
    undisclosed: "—",
    // Trends
    trendsTitle: "趋势与工作流",
    trendsSubtitle: "点击柱条可直接回到目录筛选对应案例。",
    statTotal: "收录案例",
    statPlayable: "可试玩",
    statRepos: "公开仓库",
    statModels: "模型家族",
    chartModels: "模型家族",
    chartThemes: "世界主题",
    chartTech: "常用技术栈",
    chartTimeline: "发布时间",
    chartLevels: "复现程度",
    chartSkills: "常用工具与提示",
    chartHandbook: "工作流归类",
    costSectionTitle: "耗时与费用披露",
    costSectionSummary: (cost: number, time: number) => `${time} 条披露精确耗时 · ${cost} 条披露费用`,
    methodTitle: "口径说明",
    methodBullets: [
      "数据取自公开原帖与作品页，同一作品可计入多个模型家族。",
      "「可试玩」仅计入经浏览器实测可交互的入口；其余入口仍保留直达链接。",
    ],
    // Submit & 404
    submitTitle: "提交新世界",
    submitSubtitle: "推荐 AI 构建的交互世界，附原帖或项目链接。",
    notFoundTitle: "案例未找到",
    notFoundHint: "链接可能已变更。",
    footerNote: "公开收录 · 纯静态",
    footerMethod: "口径说明",
    updatedPrefix: "更新于",
    justNow: "刚刚",
    hoursAgo: (n: number) => `${n} 小时前`,
    daysAgo: (n: number) => `${n} 天前`,
    chipKeyword: (v: string) => `“${v}”`,
    langSwitchLabel: "EN",
    langSwitchAria: "Switch to English",
  },
  en: {
    modes: { playable: "Playable", video: "Video Demos", all: "All" },
    eraScope:"Model scope", frontierOnly:"Frontier Only", includeArchive:"All (Incl. Archive)",
    brand: "WorldFeed Explore",
    navCatalog: "Catalog",
    navTrends: "Trends",
    submit: "Submit",
    skipLink: "Skip to content",
    searchPlaceholder: "Search worlds, models, stack…",
    searchModalPlaceholder: "Search titles, models (Claude / GPT / Gemini), or stack…",
    searchClear: "Clear search",
    searchOpen: "Quick search",
    searchClose: "Close",
    searchFilterCta: (q: string) => `Filter catalog for “${q}”`,
    searchEmpty: (q: string) => `No results for “${q}”`,
    searchHints: "↑↓ Navigate · Enter Open · Esc Close",
    totalCount: (n: number) => `${n} worlds`,
    // Facets & KPIs
    filter: "Filters",
    filterClose: "Close filters",
    facetModels: "Models",
    allModels: "All models",
    playable: "Playable",
    openSource: "Open Source",
    hasWorkflow: "Workflow",
    withPreview: "With Preview",
    facetThemes: "Themes",
    facetMore: "Tech Stack & Month",
    techStack: "Tech Stack",
    publishMonth: "Month",
    all: "All",
    sortFeatured: "Featured",
    sortRecent: "Newest",
    sortIngested: "Recently Added",
    sortTitle: "Title",
    viewGrid: "Cards",
    viewList: "List",
    viewTable: "Table",
    clearAll: "Clear",
    openInspector: "Preview",
    closeInspector: "Close preview",
    inspectorTitle: "Details",
    fullPage: "Full page",
    // Actions
    play: "Play",
    visit: "Visit",
    openDemo: "Play Live",
    visitDemo: "Open Demo",
    sourceCode: "Code",
    viewCode: "Source Code",
    originalPost: "Post",
    originalPage: "Page",
    viewSource: "Source",
    // Cards / Inspector / Detail
    workflow: "Workflow",
    workflowSteps: (n: number) => `${n} ${n === 1 ? "step" : "steps"}`,
    toolsAndPrompts: "Tools & Prompts",
    evidence: "Source Quotes",
    facts: "Facts",
    model: "Model",
    reproducibility: "Access",
    license: "License",
    openYes: "Open Source",
    openNo: "Closed",
    timeLabel: "Build Time",
    costLabel: "Cost",
    minutes: (n: number) => `${n} min`,
    backToCatalog: "Back to catalog",
    similarTitle: "Similar Worlds",
    author: "By",
    // Empty & Pagination
    emptyTitle: "No matching worlds",
    emptyHint: "Try shorter keywords or clear filters.",
    loadMore: "Load more",
    showAll: (n: number) => `Show all (${n})`,
    // Table headers
    colWorld: "World",
    colModel: "Model",
    colTheme: "Theme",
    colStack: "Stack",
    colActions: "Links",
    colCost: "Cost (USD)",
    colTime: "Time (min)",
    undisclosed: "—",
    // Trends
    trendsTitle: "Trends & Workflows",
    trendsSubtitle: "Click any bar to filter the catalog.",
    statTotal: "Worlds",
    statPlayable: "Playable",
    statRepos: "Public Repos",
    statModels: "Model Families",
    chartModels: "Model Families",
    chartThemes: "Themes",
    chartTech: "Top Tech Stack",
    chartTimeline: "Published",
    chartLevels: "Access Level",
    chartSkills: "Tools & Prompts",
    chartHandbook: "Workflow Patterns",
    costSectionTitle: "Reported Time & Cost",
    costSectionSummary: (cost: number, time: number) => `${time} with build time · ${cost} with cost`,
    methodTitle: "Methodology",
    methodBullets: [
      "Compiled from public creator posts and project pages; one world may use multiple model families.",
      "“Playable” counts only browser-verified demos; unverified demo links remain directly accessible.",
    ],
    // Submit & 404
    submitTitle: "Submit a World",
    submitSubtitle: "Share an AI-built interactive world with its source post or project URL.",
    notFoundTitle: "World not found",
    notFoundHint: "This link may have changed.",
    footerNote: "Public archive · Static",
    footerMethod: "Methodology",
    updatedPrefix: "Updated",
    justNow: "just now",
    hoursAgo: (n: number) => `${n}h ago`,
    daysAgo: (n: number) => `${n}d ago`,
    chipKeyword: (v: string) => `“${v}”`,
    langSwitchLabel: "中文",
    langSwitchAria: "Switch to Chinese",
  },
} as const;
