# 会议扫码签到系统

南开学校（敬慧路 / 雅馨路 / 和慧南路三校区）各类会议、教研、培训、展课活动的**扫码签到 / 签离**工具，替代排队手签。

## 功能

- **活动管理**：设置涉及校区 / 学段 / 学科（可多选）、活动名称、起止时间、地点、是否需要签离
- **签到大屏**：深色大屏，二维码与现场码每 20 秒自动轮换，实时显示已签到 / 已签离与最新动态
- **手机扫码签到**：扫码后填姓名、手机号、选校区、输入大屏上的 4 位现场码
- **后台实时面板**：应到 / 实到 / 缺席名单、2 秒自动刷新、手动补录
- **导出 Excel**：签到明细 / 应到实到统计 / 缺席名单 / 抽奖记录 四张表
- **多管理员账号**：每位教师独立账号，只管自己的活动；创建者管全部
- **名册导入**：Excel 导入，必填仅「姓名 + 校区」

## 本地运行

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe seed.py
.\.venv\Scripts\python.exe -m flask --app wsgi run --port 5000
```

浏览器打开 <http://localhost:5000/>，默认账号 `admin` / `admin123456`。

> 手机在同一 WiFi 下访问需用本机内网 IP（如 `http://192.168.1.10:5000/`），
> 并把 `BASE_URL` 环境变量设为该地址，二维码才能被手机打开。
>
> 注意：`gunicorn` 依赖 Unix 的 `fcntl`，**在 Windows 上无法运行**。本地用上面的 Flask 命令即可；
> 生产环境跑在 Linux 容器（Docker 镜像）里，gunicorn 正常工作。

## 部署到公网

见 [`deploy/部署指南.md`](deploy/部署指南.md)（面向非技术用户的图文步骤，Railway 一键部署）。

## 目录结构

```
app/            Flask 应用
  routes/       auth / admin / board / scan / api
  templates/    Jinja 模板
  static/       css / js
  models.py     User / Activity / Roster / CheckIn / Setting
  codes.py      签到码与现场码（HMAC 无状态派生，多进程安全）
  roster.py     Excel 名册导入
  exporter.py   Excel 导出
seed.py         初始化创建者账号与预置字典
tests/          pytest 验收测试
docs/superpowers/  设计文档与实现计划
```

## 测试

```powershell
.\.venv\Scripts\python.exe -m pytest tests -v
```
