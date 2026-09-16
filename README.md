# 教学论文成稿仓库

中文教学论文《失衡·校准·均衡——AI赋能下小学语文三元协同师生互动优化策略》的源稿、插图与 Word 生成脚本。

## 写作与配置

规范写在 Cursor 配置里，改稿时应自动遵循：

| 路径 | 作用 |
| --- | --- |
| `.cursor/rules/00-repo.mdc` | 只在 `main` 迭代、成稿文件名、不署个人信息 |
| `.cursor/rules/01-writing.mdc` | 论文结构、证据口径、Word 版式 |
| `.cursor/skills/teaching-paper-zh/SKILL.md` | 论文十法、图表与生成流程 |
| `.cursor/skills/de-ai-academic-zh/SKILL.md` | 去 AI 化 / 去翻译腔的学术润色 |

## 生成 Word

```bash
python3 -m pip install -r requirements.txt
./生成Word.sh
```

- 正文：`失衡·校准·均衡_AI赋能小学语文三元协同师生互动优化策略.md`
- 当前稿：`paper.docx`
- 历史轮次：`paper_v2.docx`、`paper_v3.docx` 等
