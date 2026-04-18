# VLESS Reality Python Refactor (Merged Final)

这个版本是三套重构结果合并后的最终版，取舍原则是：

- 以 **FULL_FILES** 版为运行底座，保留最完整的运维闭环和最低迁移风险。
- 吸收 **vless_python_refactor.zip** 的工程化思路，增加更清晰的安装入口与标准 CLI 入口。
- 吸收 **vless_reality_python_refactor.zip** 的 `vless-temp@.service` 模板化设计，避免每个临时节点动态生成独立 unit 文件。

## 最终取舍

- **主/临时节点、配额、IP 限制、GC、恢复、关机保存**：沿用 FULL_FILES 版的完整逻辑。
- **临时节点 systemd 管理**：改成 `vless-temp@.service` 模板实例。
- **CLI**：同时保留 `/usr/local/bin/vrctl` 与兼容层 `/usr/local/sbin/*.sh`。
- **创建临时节点**：既兼容原来的环境变量方式，也支持直接传 flags。

## 目录

- `usr/local/lib/vless-reality/vr_common.py`
  - 公共常量、路径、锁、env/json 读写、DNS/IPv4 检测、systemd 辅助函数
- `usr/local/lib/vless-reality/vr_main.py`
  - 主节点安装、Xray 安装、BBR、主配置生成
- `usr/local/lib/vless-reality/vr_runtime.py`
  - 临时节点、配额、IP 限制、GC、恢复、审计、runtime-sync
- `usr/local/lib/vless-reality/render_table.py`
  - 终端表格渲染
- `usr/local/lib/vless-reality/vrctl.py`
  - 统一 CLI 入口
- `usr/local/bin/vrctl`
  - 标准 CLI 入口
- `usr/local/sbin/*`
  - 兼容旧命令名的薄 shell 包装层
- `etc/systemd/system/vless-temp@.service`
  - 临时节点模板 unit

## 使用

```bash
bash install.sh
vim /etc/default/vless-reality
bash /root/onekey_reality_ipv4.sh
bash /root/vless_temp_audit_ipv4_all.sh
```

## 兼容命令

```bash
id=tmp001 IP_LIMIT=1 PQ_GIB=1 D=1200 vless_mktemp.sh
vless_audit.sh
pq_audit.sh
vless_clear_all.sh
pq_add.sh 40001 1
pq_del.sh 40001
ip_set.sh 40001 2 120
ip_del.sh 40001
```

## 新增能力

### 1. 临时节点模板 unit

现在统一使用 `vless-temp@.service`，实例名为：

```bash
vless-temp@vless-temp-tmp001.service
```

这样可以避免每次创建临时节点都写一个新的 unit 文件。

### 2. 直接 flags 创建临时节点

除了兼容原来的 env 调用，也可以直接这样：

```bash
vrctl vless-mktemp --duration 1200 --id tmp001 --ip-limit 1 --pq-gib 1
```

### 3. runtime-sync

如果只是重新同步 systemd / timer / restore 逻辑，而不想重复安装依赖，可以执行：

```bash
vrctl runtime-sync
```

## 说明

- 运行环境仍然保持 Debian 12 + systemd + nftables + Xray。
- `/var/lib/vless-reality/*`、`/usr/local/etc/xray/config.json`、`/etc/default/vless-reality` 等关键路径保持不变。
- 保留旧 unit/旧 wrapper 的清理兼容逻辑，方便从前两个 Python 版本平滑迁移。
