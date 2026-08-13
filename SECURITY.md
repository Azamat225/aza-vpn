# Security policy и эксплуатационные требования

## Secrets

- `.env`, `secrets/`, generated configs и runtime state исключены из Git.
- Reality private key создаётся только установленным Xray (`xray x25519`).
- Private key хранится server-only: `secrets.json` mode `0600`, active config `0640`.
- CLI/URI/status никогда не выводят private key. Ошибки native validation редактируют его.
- UUID/shortId/public key в URI — credentials доступа; не публикуйте URI.
- Backup с `/etc/aza-vpn` содержит private key и должен иметь `0600`, храниться зашифрованно или
  в доверенном root-only месте.

## X25519 parser boundary

Xray CLI output is treated as untrusted structured input. Only known field
labels are accepted; key encodings, required values, empty values, duplicate
conflicts, and unknown lines are checked fail-closed. Error messages describe
the field class but never echo a credential. `Hash32` has no storage or URI
path. The private key is redacted from native validation diagnostics and is
never passed into the URI builder.

## Cryptography

Проект не реализует X25519, VLESS, REALITY, TLS, XTLS или QUIC. UUID генерируется `xray uuid`,
X25519 — `xray x25519`, shortId — CSPRNG `secrets.token_hex(8)`. Не заменяйте эти механизмы на
`random`, timestamp или hand-written crypto.

## Supply chain

Xray загружается только с `github.com/XTLS/Xray-core/releases`. Для exact release artifact
обязателен соседний official `.dgst`; SHA-256 должен иметь известный формат и совпасть. При любой
неопределённости install/update останавливается. Resolved version сохраняется в state.

Рекомендуется после успешного теста заменить `XRAY_VERSION=latest` на фактически установленный
tag из `aza-vpn status`, закоммитить только `.env.example` policy (не `.env`) и обновлять pin
осознанно.

## Least privilege

- Xray работает как dedicated `aza-vpn`, не root.
- Порты ниже 1024 запрещены V0.1, capabilities пусты.
- Config directory `root:aza-vpn` setgid `2750`; state directory root-only `0700`.
- systemd hardening не даёт write к system paths, home, kernel/control-group settings.
- Не ослабляйте unit до root без зафиксированной технической причины.

## Change safety

- Каждый config проверяется штатным `xray run -test`.
- Candidate не заменяет active config до success.
- Active config backup + atomic rename + restart health check + rollback обязательны.
- Deployment не использует config/binary x-ui и не меняет nginx/3x-ui.
- Firewall exposure ограничен одним configured TCP-port и только явным opt-in.
- Запрещены `ufw reset`, `iptables -F`, `nft flush ruleset`.

## Reporting

Перед отправкой diagnostic output удалите:

- весь `vless://` URI;
- UUID, `pbk`, `sid`;
- содержимое `/etc/aza-vpn/secrets.json` и `config.json`;
- public IP, если вы не хотите его раскрывать.

Обычно безопасны `systemctl status`, journal (после просмотра), Xray version и exit code native
validation. Проверьте текст вручную: сторонние ошибки могут включать values из config.
