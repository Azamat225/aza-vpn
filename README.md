# AZA VPN V0.1

Небольшая самостоятельно управляемая proxy-платформа на официальном
[Xray-core](https://github.com/XTLS/Xray-core). V0.1 реализует только один data plane:

`VLESS + REALITY + XTLS Vision + RAW/TCP`

Это не форк 3x-ui и не новая реализация криптографии. Проект управляет отдельным экземпляром
Xray, клиентами, конфигурацией и deployment. Существующие nginx, x-ui/3x-ui, Docker, Redis и
старый Xray не используются и не изменяются.

> Статус проекта: код и локальные unit-тесты готовы. Работоспособность реального туннеля можно
> подтвердить только после ручного deployment на VPS и тестов с клиентских сетей.

## Границы V0.1

Реализованы:


- отдельный Xray в `/opt/aza-vpn/xray/xray`;
- отдельный `aza-xray.service` и непривилегированный пользователь `aza-vpn`;
- CLI для create/list/show/remove клиентов и status;
- генерация стандартного `vless://` URI;
- ключи REALITY и UUID только штатными командами Xray;
- official release download с обязательным `.dgst`/SHA-256;
- native config validation до каждого start/restart;
- atomic config replace, backup и rollback;
- безопасные install/update/uninstall и необязательное точечное правило UFW.

Не реализованы routing/TUN, split DNS, subscriptions, Hysteria2, XHTTP, Trojan, API, база,
сайт и платежи. Поэтому требование `RU → DIRECT, OTHER → PROXY` относится к V0.5, а не V0.1.
Текущая версия выдаёт серверный proxy-профиль; режим VPN/TUN на устройстве зависит от клиента.

## Архитектура и пути

| Назначение | Путь |
|---|---|
| Xray и Python application | `/opt/aza-vpn/` |
| Активный config и Reality secrets | `/etc/aza-vpn/` |
| Клиенты и install metadata | `/var/lib/aza-vpn/` |
| Зарезервированный каталог логов | `/var/log/aza-vpn/` |
| systemd unit | `/etc/systemd/system/aza-xray.service` |
| CLI wrapper | `/usr/local/bin/aza-vpn` |

Xray пишет в journal. Private Reality key находится только в `/etc/aza-vpn/secrets.json`
(`0600`) и в серверном `config.json` (`0640`, `root:aza-vpn`). В URI попадает только
соответствующий public key/password.

Подробнее: [архитектура](docs/ARCHITECTURE.md), [безопасность](SECURITY.md).

## Быстрая установка на Ubuntu 24.04

На локальном Windows-ПК Linux-скрипты не запускаются. После публикации репозитория выполните
на VPS самостоятельно:

```bash
git clone <YOUR_REPOSITORY_URL> aza-vpn
cd aza-vpn
cp .env.example .env
nano .env
sudo ./deploy/preflight.sh
sudo ./deploy/install.sh
sudo aza-vpn status
sudo aza-vpn client create azamat
```

Если Git не сохранил executable bit, один раз выполните:

```bash
chmod +x deploy/*.sh deploy/bin/aza-vpn deploy/lib/common.sh
```

Обязательные значения `.env`:

- `AZA_SERVER_ADDRESS` — публичный IPv4/DNS VPS;
- `AZA_VLESS_PORT` — свободный TCP-порт от 1024 до 65535, не `443`, если он занят nginx;
- `REALITY_SERVER_NAME` — SNI, принимаемый сертификатом destination;
- `REALITY_DEST` — проверяемый с VPS `host:port`;
- `XRAY_VERSION=latest` либо явный release pin.

Preflight проверяет `ss -lntup` и остановится, если порт занят. Destination проверяется именно
с VPS: TCP, TLS 1.3 и соответствие сертификата указанному SNI. Выбирать его локально за пользователя
проект не пытается. Полная процедура: [INSTALL.md](docs/INSTALL.md).

## Клиенты

```bash
sudo aza-vpn client create azamat
sudo aza-vpn client list
sudo aza-vpn client show azamat
sudo aza-vpn client remove azamat
```

`create` генерирует UUID командой установленного Xray, сохраняет клиента, создаёт candidate,
проверяет его `xray run -test`, атомарно активирует и перезапускает только `aza-xray.service`.
После успеха CLI выводит URI для импорта. См. [CLIENTS.md](docs/CLIENTS.md).

## Status и диагностика

```bash
sudo aza-vpn status
sudo aza-vpn config validate
systemctl status aza-xray.service --no-pager
journalctl -u aza-xray.service --since "10 minutes ago" --no-pager
ss -lntp | grep ':<AZA_VLESS_PORT>'
```

`status` показывает Xray version, service state, port, число клиентов, адрес и только public
REALITY information. Private key не печатается.

После импорта проверьте внешний IP, HTTPS, DNS и стабильность по
[TESTING.md](docs/TESTING.md). Один успешный Wi-Fi тест не заменяет Android/iPhone mobile tests.

## Обновление

После `git pull` проверьте `.env` и выполните:

```bash
sudo ./deploy/update.sh
sudo aza-vpn status
```

Update скачивает и проверяет новый/pinned Xray в staging, рендерит полный candidate новым кодом,
валидирует его новым бинарником и только затем меняет managed-файлы. При неудачной активации
binary/code/env/unit возвращаются к backup, а конфиг откатывается Python-транзакцией.

## Firewall

По умолчанию install/update не меняют UFW. Preflight напечатает точную команду. Явное открытие
только выбранного TCP-порта:

```bash
sudo ./deploy/install.sh --open-firewall
```

Проект не содержит `ufw reset`, `iptables -F` или `nft flush ruleset`.

## Backup

Backup содержит private key и должен оставаться root-only:

```bash
sudo install -d -m 0700 /root/aza-vpn-backup
sudo tar -C / -czf /root/aza-vpn-backup/aza-vpn-$(date +%F).tar.gz \
  etc/aza-vpn var/lib/aza-vpn
sudo chmod 0600 /root/aza-vpn-backup/aza-vpn-*.tar.gz
```

Проверьте архив через `sudo tar -tzf <archive>`, не публикуя его и не добавляя в Git.

## Удаление

```bash
sudo ./deploy/uninstall.sh
```

По умолчанию `/var/lib/aza-vpn` сохраняется. Безвозвратное удаление client state требует
явного флага:

```bash
sudo ./deploy/uninstall.sh --purge-data
```

Firewall намеренно не меняется при uninstall: правило нужно проверить вручную. Скрипт удаляет
только AZA paths/unit/wrapper и не обращается к nginx, x-ui, старому Xray, Docker или Redis.

## Локальные тесты

Linux/macOS:

```bash
PYTHONPATH=src python3.12 -m compileall -q src tests
PYTHONPATH=src python3.12 -m unittest discover -s tests -v
```

PowerShell:

```powershell
$env:PYTHONPATH = (Resolve-Path src).Path
python.exe -m compileall -q src tests
python.exe -m unittest discover -s tests -v
```

Тесты используют только фиктивные credentials, явно обозначенные как fixtures. Они не запускают
Xray-сервер, systemd, UFW, apt и не проверяют внешние серверные порты.

## Официальные источники формата

- [REALITY settings](https://xtls.github.io/en/config/transports/reality.html)
- [Transport configuration / RAW](https://xtls.github.io/en/config/transport.html)
- [Xray command line: `run -test`, `uuid`, `x25519`](https://xtls.github.io/en/document/command.html)
- [Official releases](https://github.com/XTLS/Xray-core/releases)
- [Official installer checksum workflow](https://github.com/XTLS/Xray-install/blob/main/install-release.sh)

## Roadmap

- **V0.1** — VLESS + Reality + Vision + RAW/TCP; CLI, deployment, client URI.
- **V0.2** — Hysteria2/QUIC.
- **V0.3** — VLESS XHTTP.
- **V0.4** — Trojan TLS.
- **V0.5** — TUN/split routing: `RU → DIRECT`, `OTHER → PROXY`.
- **V0.6** — split DNS.
- **V0.7** — subscription URL.
- **V0.8** — FastAPI control plane.
- **V0.9** — users/nodes/revocation/monitoring.
- **V1.0** — multi-node, health checking и transport selection.
