"""Testcase generation chains with planning and building stages."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from langchain.schema import HumanMessage, SystemMessage

from chatbot.content_processor import ContentSegment


@dataclass
class TestcaseModeConfig:
    name: str
    planner_prompt: str
    builder_prompt: str
    system_prompt: Optional[str]
    context_limit: int
    metadata: Dict[str, str]
    layout: str = "detailed"


@dataclass
class TestcaseFieldSchema:
    key: str
    label: str
    required: bool = False
    description: Optional[str] = None


@dataclass
class TestPlanSection:
    title: str
    checklist: List[str]

    def as_dict(self) -> Dict[str, Any]:
        return {"title": self.title, "checklist": self.checklist}


@dataclass
class TestcaseLayout:
    name: str
    description: str
    fields: List[TestcaseFieldSchema]
    plan_sections: List[TestPlanSection]


@dataclass
class TestcaseCase:
    title: str
    field_values: Dict[str, Any] = field(default_factory=dict)
    raw_text: Optional[str] = None


@dataclass
class TestcaseModule:
    name: str
    layout: str
    goal: Optional[str] = None
    cases: List[TestcaseCase] = field(default_factory=list)
    fallback_content: Optional[str] = None


@dataclass
class TestcaseDocument:
    mode: str
    modules: List[TestcaseModule]
    metadata: Dict[str, Any] = field(default_factory=dict)
    planner_notes: List[str] = field(default_factory=list)
    plan_summary: List[TestPlanSection] = field(default_factory=list)

    def to_markdown(self, layouts: Dict[str, TestcaseLayout]) -> str:
        lines = [f"# 测试用例（模式：{self.mode}）"]
        if self.metadata:
            lines.append(f"> Metadata: {self.metadata}")
        if self.plan_summary:
            lines.append("\n## 测试方案摘要")
            for section in self.plan_summary:
                lines.append(f"### {section.title}")
                for item in section.checklist:
                    lines.append(f"- {item}")

        for index, module in enumerate(self.modules, start=1):
            lines.append(f"\n## 模块 {index}: {module.name}")
            if module.goal:
                lines.append(f"> 模块目标：{module.goal}")

            layout = layouts.get(module.layout)
            if module.cases and layout:
                for case_index, case in enumerate(module.cases, start=1):
                    lines.append(f"### 用例 {case_index}: {case.title}")
                    for field in layout.fields:
                        if field.key == 'title':
                            continue
                        value = case.field_values.get(field.key)
                        if value:
                            lines.append(f"- {field.label}: {value}")
                    if case.raw_text:
                        lines.append(case.raw_text)
            elif module.fallback_content:
                lines.append(module.fallback_content)

        return "\n".join(lines).strip() + "\n"

    def to_dict(self) -> Dict[str, Any]:
        modules_payload: List[Dict[str, Any]] = []
        for module in self.modules:
            modules_payload.append(
                {
                    "name": module.name,
                    "layout": module.layout,
                    "goal": module.goal,
                    "fallback_content": module.fallback_content,
                    "cases": [
                        {
                            "title": case.title,
                            "field_values": case.field_values,
                            "raw_text": case.raw_text,
                        }
                        for case in module.cases
                    ],
                }
            )

        return {
            "mode": self.mode,
            "metadata": self.metadata,
            "planner_notes": self.planner_notes,
            "plan_summary": [section.as_dict() for section in self.plan_summary],
            "modules": modules_payload,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


class TestcaseGenerator:
    """Runs a two-stage plan→build pipeline for PRD-based test cases."""

    def __init__(self, llm, memory_manager, layout_config: Optional[Dict[str, Any]] = None):
        self.llm = llm
        self.memory = memory_manager
        self.layouts = self._load_layouts(layout_config or {})
        if not self.layouts:
            self.layouts = self._load_layouts(
                {
                    "basic": {
                        "description": "默认模板",
                        "case_fields": [
                            {"key": "title", "label": "用例标题", "required": True},
                            {"key": "preconditions", "label": "前置条件"},
                            {"key": "steps", "label": "操作步骤"},
                            {"key": "expected", "label": "预期结果"},
                        ],
                        "plan_sections": [
                            {
                                "title": "基础检查",
                                "checklist": [
                                    "覆盖主流程与关键异常。",
                                    "验证兼容性与性能基线。",
                                ],
                            }
                        ],
                    }
                }
            )

    def generate(self, segments: List[ContentSegment], mode: TestcaseModeConfig) -> TestcaseDocument:
        context = self._build_context(segments, mode.context_limit)
        plans = self._plan_modules(context, mode)
        layout = self.layouts.get(mode.layout) or next(iter(self.layouts.values()))
        modules: List[TestcaseModule] = []

        for plan in plans:
            raw_output = self._build_cases(context, plan, mode, layout)
            module_obj = self._parse_module_output(plan, raw_output, layout)
            modules.append(module_obj)

        summary_text = f"Generated {len(modules)} modules for mode {mode.name} (version {mode.metadata.get('version', 'n/a')})."
        self.memory.add_document_summary(summary_text)

        return TestcaseDocument(
            mode=mode.name,
            modules=modules,
            metadata=mode.metadata,
            planner_notes=plans,
            plan_summary=self._build_plan_summary(mode, layout, modules),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_layouts(self, config: Dict[str, Any]) -> Dict[str, TestcaseLayout]:
        layouts: Dict[str, TestcaseLayout] = {}
        for name, payload in config.items():
            fields = [
                TestcaseFieldSchema(
                    key=item.get('key', f'field_{index}'),
                    label=item.get('label', item.get('key', f'field_{index}')),
                    required=item.get('required', False),
                    description=item.get('description'),
                )
                for index, item in enumerate(payload.get('case_fields', []))
            ]
            if not any(field.key == 'title' for field in fields):
                fields.insert(0, TestcaseFieldSchema(key='title', label='用例标题', required=True))

            plan_sections = [
                TestPlanSection(
                    title=section.get('title', '质量关注点'),
                    checklist=section.get('checklist', []),
                )
                for section in payload.get('plan_sections', [])
            ]

            layouts[name] = TestcaseLayout(
                name=name,
                description=payload.get('description', ''),
                fields=fields,
                plan_sections=plan_sections,
            )
        return layouts

    @staticmethod
    def _format_template(template: str, **kwargs) -> str:
        """Safely substitute {key} placeholders without touching其他花括号."""

        result = template
        for key, value in kwargs.items():
            result = result.replace(f'{{{key}}}', str(value))
        return result

    def _plan_modules(self, context: str, mode: TestcaseModeConfig) -> List[str]:
        prompt = self._format_template(mode.planner_prompt, context=context, mode=mode.name)
        messages = [
            SystemMessage(content=mode.system_prompt or "你是测试规划专家。"),
            HumanMessage(content=prompt),
        ]
        response = self.llm.invoke(messages).content.strip()
        plans = [line.strip("- ") for line in response.splitlines() if line.strip()]
        return plans or ["通用功能"]

    def _build_cases(
        self,
        context: str,
        plan: str,
        mode: TestcaseModeConfig,
        layout: TestcaseLayout,
    ) -> str:
        layout_schema = self._render_layout_schema(layout)
        prompt = self._format_template(
            mode.builder_prompt,
            context=context,
            module=plan,
            mode=mode.name,
            layout_schema=layout_schema,
        )
        messages = [
            SystemMessage(content=mode.system_prompt or "你是测试用例专家。"),
            HumanMessage(content=prompt),
        ]
        response = self.llm.invoke(messages).content.strip()
        return response

    def _parse_module_output(self, module_name: str, raw_response: str, layout: TestcaseLayout) -> TestcaseModule:
        try:
            payload = json.loads(raw_response)
            goal = payload.get('module_goal')
            cases_payload = payload.get('cases', [])
            cases: List[TestcaseCase] = []
            for case in cases_payload:
                title = case.get('title') or f"{module_name} 用例"
                field_values = {}
                for field in layout.fields:
                    if field.key == 'title':
                        continue
                    value = case.get(field.key)
                    if value:
                        field_values[field.key] = value
                raw_text = case.get('raw_text')
                cases.append(TestcaseCase(title=title, field_values=field_values, raw_text=raw_text))

            if cases:
                return TestcaseModule(
                    name=module_name,
                    layout=layout.name,
                    goal=goal,
                    cases=cases,
                )
        except (json.JSONDecodeError, TypeError):
            pass

        return TestcaseModule(
            name=module_name,
            layout=layout.name,
            fallback_content=raw_response.strip(),
        )

    def _render_layout_schema(self, layout: TestcaseLayout) -> str:
        lines = ["模板字段要求："]
        for field in layout.fields:
            badge = "必填" if field.required else "选填"
            description = f"（{field.description}）" if field.description else ""
            lines.append(f"- {field.label}（key={field.key}，{badge}）{description}")
        return "\n".join(lines)

    def _build_plan_summary(
        self,
        mode: TestcaseModeConfig,
        layout: TestcaseLayout,
        modules: List[TestcaseModule],
    ) -> List[TestPlanSection]:
        sections = layout.plan_sections or [
            TestPlanSection(
                title="质量关注点",
                checklist=[
                    "确保主流程可用，关键接口通过。",
                    "验证兼容性与性能基线。",
                ],
            )
        ]
        module_list = ", ".join(module.name for module in modules[:5])
        result: List[TestPlanSection] = []
        for section in sections:
            checklist = [
                item.replace("{modules}", module_list or "当前模块").replace("{mode}", mode.name)
                for item in section.checklist
            ]
            result.append(TestPlanSection(title=section.title, checklist=checklist))

        if module_list and result:
            result[0].checklist.append(f"重点模块：{module_list}")

        return result

    def _build_context(self, segments: List[ContentSegment], limit: int) -> str:
        chunks: List[str] = []
        for segment in segments:
            snippet = segment.content
            if len(snippet) > 4000:
                snippet = snippet[-4000:]
            chunks.append(f"### {segment.type}:{segment.source}\n{snippet}")
        text = "\n\n".join(chunks)
        if len(text) > limit:
            text = text[-limit:]
        doc_summary = self.memory.get_document_overview()
        if doc_summary:
            text = doc_summary + "\n\n" + text
        return text
