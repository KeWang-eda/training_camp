# 背景

目前的软件开发流程中，作为测试人员，编写测试用例是一项基本技能，其质量对需求验证、测试阶段乃至最终的产品上线具有重要影响，但用例设计需要耗费大量人力，仅凭人工方法难以保证全面的测试覆盖率和避免人为错误。

大型语言模型（LLM）的出现为测试 case 生成带来了新的思路。这些模型具备理解自然语言和上下文的能力。通过分析需求，LLM 有望自动完成创建测试用例这项费时的工作。

# 要求

1. ## 实现一个前端操作页面

- 支持直接粘贴PRD（Product Requirements Document，产品需求文档）全文
  - 或者填写飞书文档链接，使用接口获取文档内容（可选，加分项）[Obtain the plain text content of the document](https://open.larkoffice.com/document/server-docs/docs/docs/docx-v1/document/raw_content) or [Get docs content](https://open.larkoffice.com/document/docs/docs-v1/get)
  - 非文本内容，比如UI图、流程图如何解析和输入给LLM（可选，加分项）
- **根据PRD内容生成测试用例（Test Case）**，并展示（可使用前端库，思维导图或者表格形式均可）
- 测试用例需按照一定格式生成，建议：标题-前置条件-操作步骤-预期结果

```Markdown
# 用户登录
## 输入正确的用户名和密码进行登录
### 前置条件
用户已经注册并处于登出状态
### 操作步骤
1. 打开登录界面
2. 在用户名输入框中输入正确的用户名
3. 在密码输入框中输入正确的密码
4. 点击登录按钮
### 预期结果
1. 用户成功登录，跳转到主页面
```

1. ## 实现自动化评测

LLM的效果的优化依赖持续的评测，你需要按照以下方式进行效果评测：

- 按照测试用例格式人工输出一份功能测试用例
- 自己设计评价指标，能说清楚设计指标的逻辑性，计算方式即可。
- 使用设计的指标将生成的测试case和人工写的case做对比，不断优化效果

注：这里的评测目的是指导算法迭代，修改了Prompt、修改了算法怎么评估这一版比上一版好。是一个离线的、大批量的、线下的测试动作。不是用例生成过程中可能有的self-reflection（自省）环节。

1. ## AI辅助工具的限制

具体产品/技术方案，你可以咨询ChatGPT、豆包等AI工具

代码实现可以使用[trae](https://www.trae.com.cn/)/cursor/claude code等工具辅助

后端可以字节[coze](https://www.coze.cn/)、Dify等agent builder平台实现，也可以使用代码实现（比如基于LangChain/LangGraph，编程语言不限）

不得抄袭他人已有的项目（包含prompt和代码）

# 物料/参考信息

## 测试企业

> 用于创建应用读取飞书文档

可以自行创建飞书企业

## 示例需求

> 可以自己找合适的，不要求一定使用这个

[B端产品登录功能详解（附需求文档范文） – 人人都是产品经理](https://www.woshipm.com/pd/4505867.html)

## 如何设计测试用例

《软件测试的艺术》，第四章-测试用例的设计

[质量保障之道 - 测试开发是做什么的（WIP）](https://bytedance.larkoffice.com/wiki/BqrYwybP2i5MmRkOX7NcAlOknqc)

## 如何写Prompt

[课程培训 - Prompt Engineering 快速入门](https://bytedance.larkoffice.com/wiki/Hej2wRBwPigMoUkXwRAc7GianwV)

## 大模型平台

推荐[字节火山引擎](https://www.volcengine.com/product/ark)，注册账号就有免费额度（不够用可以给我们反馈），可使用Doubao、DeepSeek、Kimi等模型。是否使用深度思考模型，自己取舍。