# 接口体检 2026-10-18

- 主机：LAPTOP-B334PRFI · Windows 11
- Python：3.12.14
- 结果：**4/6 个接口返回 200**

| 接口 | 用途 | 状态 | 延迟 | 大小 | 证据 | 备注 |
|---|---|---|---|---|---|---|
| UniProt REST | 人类糖蛋白实验证据检索（F1 数据源） | `200` | 1388 ms | 0 KB | X-Total-Results=1381 | 期望 200，且 X-Total-Results = 1381 |
| GlyGen | 单蛋白糖基化详情（F1 位点证据） | `200` | 60831 ms | 584 KB | {"mass": {"chemical_mass": 43912.0}, "gene_names": [{"name": "IGHG1", "type": "recommended… | 必须 GET；POST 会 500；响应约 600 KB |
| GlyConnect | 糖蛋白/糖链关联（F2 备选数据源） | `500` | 2262 ms | 2 KB | <!DOCTYPE html> <html lang="en">     <head>         <title>Error</title>         <link rel… | 文档给的路径 2026-10-18 不通，这里探活 |
| GlyTouCan | 糖链结构标识（F2/F3 结构查询） | `404` | 2244 ms | 0 KB | {"errcode":"E_NOT_FOUND","contents":{"message":"Endpoint not found"},"logs":{"url":"http:/… | 文档给的路径 2026-10-18 返回 404，这里探活 |
| KEGG REST | 通路信息（F3 工具之一） | `200` | 4562 ms | 0 KB | pathway	KEGG pathway maps path	587 entries 	Last update 2026/10/15 	Kanehisa Laboratories … | 期望 200 且返回纯文本 |
| PubChem PUG REST | 化合物属性查询（F3 工具之一） | `200` | 2070 ms | 0 KB | MolecularFormula=C6H12O6 | 期望 200 且 JSON 内含 MolecularFormula |

> 判定口径：`200` 可用；`4xx/5xx` 记为不可用，需换路径或换数据源；`ERR` 是网络层失败。
> 同一接口连续两次失败再下结论，单次超时可能只是网络抖动。
> “证据”列保留接口原始返回，英文内容来自上游服务，不对机器输出做翻译改写；中文“备注”列给出本次判定。
