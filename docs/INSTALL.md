# Установка и deployment

## 1. Подготовка `.env`

```bash
cp .env.example .env
nano .env
```

Пример формы (значения адреса, порта и destination должны быть вашими):

```dotenv
AZA_SERVER_ADDRESS=<PUBLIC_IPV4>
AZA_SERVER_LABEL=Germany-01
AZA_VLESS_PORT=<FREE_NON_PRIVILEGED_TCP_PORT>
AZA_LISTEN_ADDRESS=0.0.0.0
REALITY_SERVER_NAME=<CERTIFICATE_SNI>
REALITY_DEST=<HOST:PORT>
REALITY_FINGERPRINT=chrome
XRAY_VERSION=latest
XRAY_LOG_LEVEL=warning
```

Не ставьте TCP 443, если его слушает nginx. V0.1 требует порт `1024..65535`, потому что Xray
работает без root и без `CAP_NET_BIND_SERVICE`.

`REALITY_SERVER_NAME` должен входить в сертификат, который destination возвращает при TLS
handshake. `REALITY_DEST` не выбирается автоматически: сетевой путь и TLS проверяются с VPS.
Не делайте вывод о пригодности destination по проверке с локального Windows-ПК.

## 2. Preflight

```bash
sudo ./deploy/preflight.sh
```

Он проверяет:

- Linux и Ubuntu/Debian family;
- root и Python 3.12+;
- architecture (`x86_64 → Xray-linux-64.zip`, также предусмотрен arm64);
- `curl`, `unzip`, `sha256sum`, `ss` и остальные необходимые utilities;
- структуру `.env` без shell `source`/`eval`;
- свободный configured TCP-port и печатает `ss -lntup` при конфликте;
- существующие nginx/x-ui как информацию: `Existing service detected. It will not be modified.`;
- ≥200 MiB под `/opt` и writable parent directories;
- доступ к official GitHub release API;
- TCP/TLS 1.3/certificate destination с заданным SNI;
- UFW status без изменения rules.

Ошибка preflight ничего не устанавливает и не останавливает.

## 3. Install

```bash
sudo ./deploy/install.sh
```

Install ставит только недостающие базовые пакеты через apt, без `upgrade`, скачивает release и
соответствующий `.dgst` с `github.com/XTLS/Xray-core/releases`, извлекает SHA-256 из официального
формата и сравнивает с `sha256sum`. Непонятный/отсутствующий `.dgst` — hard failure.

Для `XRAY_VERSION=latest` tag сначала читается из official `releases/latest` API, после чего
resolved tag записывается в `/var/lib/aza-vpn/install.json`. В конце выводятся requested,
installed и architecture. Явный pin допускает `vX.Y.Z` или `X.Y.Z`.

Далее Xray сам выполняет:

```text
xray x25519  -> private key + public key/password
xray uuid    -> при создании каждого клиента
```

shortId создаётся Python `secrets.token_hex(8)` (16 hex characters). X25519 в Python не
реализуется.

Перед первым `systemctl start` install выполняет `aza-vpn config validate`; unit повторяет
native validation через `ExecStartPre`.

### X25519 output compatibility

The installer invokes the downloaded Xray binary directly. Its strict parser
accepts the known label pairs `Private key / Public key`,
`PrivateKey / PublicKey`, `PrivateKey / Password`, and
`PrivateKey / Password (PublicKey) / Hash32`. Labels are case-insensitive and
tolerate horizontal whitespace. The parenthetical alias is accepted only as
`Password (PublicKey)`, not for arbitrary labels. Missing, empty, unknown,
malformed, or conflicting fields stop installation without printing credential
values.

`Password` and `Password (PublicKey)` are modern names of the client-side
X25519 credential. `Hash32` is ignored and is never persisted. The private
value remains server-only.

### Resume an interrupted install

An exact `.aza-vpn-managed` marker proves ownership of the managed paths;
`/var/lib/aza-vpn/install.json` proves that installation reached an active
service. If a previous run failed before the completion record (for example,
while parsing `xray x25519`), update the repository and rerun:

```bash
git pull --ff-only
sudo ./deploy/preflight.sh
sudo ./deploy/install.sh
```

No `rm`, uninstall, nginx/x-ui stop, or cleanup is required. A resumed install
validates the marker/account, accepts an occupied configured port only when it
belongs to `/opt/aza-vpn/xray/xray`, regenerates missing managed state, validates
the candidate, and writes the completion record only after the service is active.

## 4. Firewall opt-in

По умолчанию никакое правило не добавляется. Если UFW active:

```bash
sudo ufw allow <PORT>/tcp comment 'aza-vpn VLESS'
```

Либо единственный opt-in:

```bash
sudo ./deploy/install.sh --open-firewall
```

Он выполняет только `ufw allow <configured-port>/tcp`. Другие firewall rules не затрагиваются.

## 5. Проверка установки

```bash
sudo aza-vpn status
sudo aza-vpn config validate
systemctl status aza-xray.service --no-pager
ss -lntp | grep ':<PORT>'
journalctl -u aza-xray.service --since "10 minutes ago" --no-pager
```

Затем:

```bash
sudo aza-vpn client create azamat
```

Не публикуйте полный URI в issue/chat: UUID, `pbk` и `sid` являются клиентскими credentials.

## Update

```bash
git pull --ff-only
nano .env
sudo ./deploy/update.sh
```

Если порт изменён, update проверит новый до изменений. Старое UFW-правило автоматически не
удаляется. Новый rule добавляется только с `--open-firewall`.

## Failure и recovery

Config lifecycle:

```text
config.json.new -> xray run -test -> config.json.bak -> atomic replace -> restart
                                                         failure -> restore -> restart old
```

Если rollback restart тоже не прошёл:

```bash
sudo systemctl status aza-xray.service --no-pager
sudo journalctl -u aza-xray.service -n 100 --no-pager
sudo /opt/aza-vpn/xray/xray run -test -config /etc/aza-vpn/config.json
sudo ls -l /etc/aza-vpn/config.json*
```

Не вставляйте `config.json` или `secrets.json` в публичную диагностику.
