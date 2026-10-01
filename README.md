# StallSpan 市集摊档开间

沿街段一维 First-Fit 开间分配，挡柱不可被摊位跨越，输出分配图与放不下清单。

技术栈：Python 3.12 / FastAPI / SQLAlchemy / PostgreSQL / Vue 3 / TypeScript / Vite

## 启动

```bash
docker compose up --build
```

| 服务 | 地址 |
| --- | --- |
| 前端 | http://localhost:4700 |
| API | http://localhost:9700 |
| API 文档 | http://localhost:9700/docs |
| Postgres | localhost:5448 |

健康检查：`GET http://localhost:9700/api/health`

## 使用说明

1. 在「集日」「街段」确认开市日与可用宽度。
2. 在「摊主」「挡柱」维护需求宽度与障碍位置。
3. 在「摊主」页可一次提交合并两个仍有效摊主为新占位摊：宽为两摊之和、优先取较高者；合并本身不写运行行，若合并宽在任一柱间都塞不下则整单失败、原摊状态不变。
4. 打开「分配带」现算预览（不落库），确认无误后点「确认开间」才写运行行。
5. 在「放不下」查看无法安置的摊位。

## 开发与测试

```bash
docker compose exec api pytest -q
```
