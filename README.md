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
3. 打开「分配图」执行一维开间分配。
4. 在「放不下」查看无法安置的摊位。

## 合并占位

在「摊主」页一次提交选定两个仍有效摊主,合成一个新占位摊:

- 新摊宽度 = 两摊宽度之和,优先级取两者较高者;合并来源记录在案。
- 原两摊在列表标「已合并退出」,分配图与放不下不再单独点名,新摊参与随后现算/确认。
- 合并宽塞不下任一柱间空档时整单失败:新摊不出现、原两摊状态不变、运行行数不增。
- 对已撤出或已合并退出的摊再合并会被拒绝(与塞不下文案不同)。
- 合并本身不写分配运行行,只有重新分配(确认开间)才落库。

接口:`POST /api/vendors/merge` 请求体 `{"vendor_ids": [id甲, id乙]}`;`POST /api/vendors/{id}/withdraw` 把有效摊标为已撤出。

## 开发与测试

```bash
docker compose exec api pytest -q
```
