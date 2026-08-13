# Архитектура V0.1

## Компоненты

- Xray-core — единственный data plane и реализация VLESS/REALITY/XTLS.
- `aza_vpn.cli` — локальный root-admin control tool без network API.
- JSON repository — adapter client state в `/var/lib/aza-vpn/clients.json`.
- strict template renderer — подставляет только JSON-encoded values.
- `ConfigApplier` — native validation, atomic activation и rollback.
- shell deployment — official download/checksum, users, permissions, unit lifecycle.

Repository adapter отделён от моделей/сервиса, поэтому в следующих версиях его можно заменить
на PostgreSQL без переноса protocol generation в database layer.

## Client create transaction

```text
validate name
  -> xray uuid
  -> build new in-memory state
  -> write state atomically
  -> render /etc/aza-vpn/config.candidate.json
  -> xray run -test -format=json -c config.candidate.json
  -> backup active config
  -> os.replace(candidate, active)
  -> systemctl restart aza-xray.service
       success -> keep state and URI
       failure -> restore config, restart old, restore state
```

Операции защищены exclusive lock. Atomic rename выполняется внутри того же filesystem/directory.
Backup хранит private key и наследует `0640`.

## Reality key boundary

`xray.keys` converts version-dependent CLI labels into
`RealityKeyPair(private_key, client_key)`. Persistent secrets use the same
semantic `client_key` name but can read the V0.1 legacy `public_key` property.
The server template consumes only `private_key`; the VLESS URI builder receives
only `client_key` and serializes it as ecosystem-compatible `pbk`. `Hash32` is
discarded at the parser boundary.

## Xray server config

Один inbound:

- protocol `vless`;
- clients: `id`, `email`, `flow=xtls-rprx-vision`;
- `decryption=none`;
- stream `network=raw`, `security=reality`;
- current `realitySettings.target`, `serverNames`, `privateKey`, `shortIds`.

Один outbound: `freedom`, tag `direct`. Routing rules, GeoIP и DNS отсутствуют намеренно.

## Privilege boundary

CLI mutation запускается root, потому что меняет root-owned state/config и systemd service.
Xray после этого работает как system user `aza-vpn`, без capabilities. Поэтому listener ограничен
non-privileged port. Service получает read-only system view и только AF_UNIX/AF_INET/AF_INET6.

## Неизбежное crash-window ограничение

State и Xray config находятся в разных файлах, поэтому атомарной multi-file transaction на уровне
filesystem нет. Код откатывает оба при обрабатываемой ошибке, но внезапное питание/kill в несколько
инструкций между state replace и config replace может потребовать `sudo aza-vpn config apply` для
повторной синхронизации. Это ограничение локального JSON backend; database transaction появится в
будущем control plane.
