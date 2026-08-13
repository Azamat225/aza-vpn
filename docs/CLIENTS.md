# Клиенты и URI

V0.1 выдаёт sharing URI вида:

```text
vless://<UUID>@<ADDRESS>:<PORT>?encryption=none&flow=xtls-rprx-vision&security=reality&sni=<SNI>&fp=<FP>&pbk=<CLIENT_KEY>&sid=<SHORT_ID>&type=tcp#<LABEL>
```

Query и fragment кодируются через стандартный URL encoder. В URI нет private key, server paths,
`REALITY_DEST` или других server-only values. `type=tcp` — широко используемое в sharing URI
имя RAW/TCP transport; серверный актуальный config использует `network: raw`.

## Управление

```bash
sudo aza-vpn client create azamat
sudo aza-vpn client list
sudo aza-vpn client show azamat
sudo aza-vpn client remove azamat
```

Имена: 1–64 lowercase ASCII characters; разрешены цифры, `.`, `_`, `-`. Remove немедленно
исключает UUID из server config после successful native validation/restart. Сохранённый на
устройстве URI после этого больше не должен проходить authentication.

## Приложения

Проверяйте свежую версию приложения и его core перед import:

- Windows: v2rayN с поддержкой VLESS + REALITY + Vision;
- Android: v2rayNG либо Hiddify/HAPP build с этой комбинацией;
- iPhone: Hiddify/HAPP или другой клиент, который явно импортирует `pbk`, `sid`, `sni`,
  `xtls-rprx-vision` и TCP/RAW.

Название приложения само по себе не гарантирует поддержку конкретной версии формата. После
import откройте профиль и сверьте address, port, UUID, SNI, public key, shortId, fingerprint и
flow. Не заменяйте REALITY public key/private key местами.

## REALITY client credential naming

The same client-side X25519 value has different field names at different
boundaries:

- modern `xray x25519` output: `Password` or `Password (PublicKey)`;
- older Xray output/state terminology: `PublicKey` / `public_key`;
- current Xray outbound JSON: `password`;
- compatible VLESS sharing URI: `pbk`.

AZA VPN stores it internally as `client_key` and reads legacy `public_key`
state for compatibility. v2rayNG source, v2rayN share-link examples, and the
Hiddify URL scheme use `pbk`. HAPP should be checked with the installed client
version. `Hash32` and the server private key are never placed in the URI.

Format references checked for this compatibility decision:

- [current Xray REALITY client field](https://xtls.github.io/en/config/transports/reality.html);
- [v2rayNG URI parser/serializer source](https://github.com/2dust/v2rayNG/blob/master/V2rayNG/app/src/main/java/com/v2ray/ang/fmt/FmtBase.kt);
- [Hiddify URL scheme](https://github.com/hiddify/hiddify-app/wiki/URL-Scheme);
- [v2rayN VLESS REALITY share-link example](https://github.com/2dust/v2rayN/issues/7135).

## Import

1. Выполните `sudo aza-vpn client show <name>` в доверенной admin session.
2. Скопируйте полный URI.
3. Используйте `Import from clipboard/URL` в клиенте.
4. Проверьте распознанные поля.
5. Включите профиль и выполните [TESTING.md](TESTING.md).

V0.1 не генерирует QR, не отправляет URI по сети и не публикует subscription URL.

## Режим устройства

Чтобы приложения устройства действительно шли через профиль, в клиенте обычно нужен VPN/TUN
режим. Конкретные названия переключателей зависят от приложения. Split routing российских
назначений и split DNS пока не реализованы проектом; нельзя считать V0.1 выполнением будущей
схемы always-on `RU → DIRECT / OTHER → PROXY`.
