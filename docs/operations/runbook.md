# FDE AI Platform — 运维操作手册

## 一、服务启动/停止

### Docker Compose (单机部署)

```bash
# 启动全部服务
docker compose -f deploy/docker-compose.prod.yml up -d

# 查看状态
docker compose -f deploy/docker-compose.prod.yml ps

# 查看日志
docker compose -f deploy/docker-compose.prod.yml logs -f fde-backend

# 停止
docker compose -f deploy/docker-compose.prod.yml down

# 重启单个服务
docker compose -f deploy/docker-compose.prod.yml restart fde-backend
```

### Kubernetes (集群部署)

```bash
# 安装
helm upgrade --install fde-platform ./deploy/helm/fde-platform \
    --namespace fde-production --create-namespace \
    --set backend.secrets.jwtSecretKey=$JWT_SECRET \
    --set backend.secrets.databaseUrl=$DATABASE_URL

# 查看状态
kubectl get pods -n fde-production -w

# 扩缩容
kubectl scale deployment fde-platform-backend -n fde-production --replicas=5

# 重启
kubectl rollout restart deployment -n fde-production
```

### Systemd (测试服务器)

```bash
# 服务文件: /etc/systemd/system/fde.service
sudo systemctl start fde
sudo systemctl stop fde
sudo systemctl restart fde
sudo systemctl status fde
sudo journalctl -u fde -f
```

---

## 二、健康检查

```bash
# 主健康检查
curl http://localhost:8000/health

# Nginx 代理
curl https://fde.example.com/health

# Prometheus metrics
curl http://localhost:8000/metrics

# PostgreSQL
pg_isready -U fde -d fde_platform

# Redis
redis-cli ping

# Qdrant
curl http://localhost:6333/health

# Grafana (port 3000)
curl http://localhost:3000/api/health
```

---

## 三、数据库备份与恢复

```bash
# 备份 (pg_dump)
pg_dump -U fde -h localhost fde_platform > /backup/fde_$(date +%Y%m%d_%H%M).sql

# 自动备份 cron (每天 3:00 AM)
# crontab -e
# 0 3 * * * pg_dump -U fde fde_platform > /backup/fde_$(date +\%Y\%m\%d).sql

# 恢复
psql -U fde -d fde_platform < /backup/fde_20260703.sql
```

---

## 四、日志查看与故障排查

### 应用日志

```bash
# Docker
docker logs fde-backend-prod --tail 100 -f

# Systemd
sudo journalctl -u fde -n 100 -f

# 日志文件
tail -f /var/log/fde/app.log
```

### 常见问题

| 问题 | 排查命令 | 解决 |
|------|---------|------|
| 服务不可达 | `curl localhost:8000/health` | 检查后端容器/systemd 状态 |
| 数据库连接失败 | `pg_isready -U fde` | 检查 PostgreSQL 容器/端口 |
| RAG 检索慢 | `curl localhost:6333/health` | 检查 Qdrant 索引 |
| OOM | `docker stats` / `kubectl top pods` | 增加内存限制 |
| TLS 证书过期 | `certbot certificates` | 运行 certbot renew |

---

## 五、扩容/缩容

### Docker (改 compose + 重启)

```bash
# 编辑 deploy/docker-compose.prod.yml 中 fde-backend 的 deploy.resources.limits
docker compose -f deploy/docker-compose.prod.yml up -d --scale fde-backend=3
```

### Kubernetes (HPA 自动)

```bash
# HPA 已配置 (CPU > 70% 自动扩容 2→10)
kubectl get hpa -n fde-production

# 手动缩放
kubectl scale deployment fde-platform-backend -n fde-production --replicas=5
```

---

## 六、证书续期

```bash
# Let's Encrypt (Docker)
docker compose -f deploy/docker-compose.prod.yml run --rm certbot renew

# Let's Encrypt (standalone)
certbot renew --webroot -w /var/www/certbot

# 查看证书状态
certbot certificates
```

---

## 七、安全加固检查

```bash
# Python 依赖漏洞
pip-audit

# npm 依赖漏洞
cd frontend/map-ai && npm audit

# 端口扫描 (从外部)
nmap -p 80,443,8000,5432,6379,6333 217.142.246.70

# OCI 安全列表 (Oracle Cloud)
# 登录 OCI Console → Networking → Virtual Cloud Networks → Security Lists
# 确保只开放 TCP 80, 443 (生产) 或 TCP 22, 80, 443, 8443 (测试)
```

---

## 八、监控与告警

| 仪表板 | URL | 说明 |
|--------|-----|------|
| Grafana | https://fde.example.com:3000 | QPS, 延迟, 错误率, 会话数, Worker状态 |
| Prometheus | https://fde.example.com:9090 | 指标原始数据 |
| Prometheus Alerts | https://fde.example.com:9090/alerts | 活跃告警 |

### 告警级别

- **critical**: HighErrorRate, WorkerFailureRate, ServiceDown
- **warning**: HighLatency, RAGLatencySpike
- **info**: NoActiveSessions

---

## 九、测试服务器信息

- **IP**: 217.142.246.70
- **系统**: Oracle ARM 2C/11G/96G, Ubuntu
- **SSH**: `ssh -i ~/ssh/arm.key ubuntu@217.142.246.70`
- **OCI 端口**: 需在 Oracle Cloud Console 手动开放 TCP 8443 (已配置 iptables)
- **Dify**: http://217.142.246.70 (Docker, 12 容器)