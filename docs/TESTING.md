# Ручной test plan после deployment

Не отмечайте VPN/proxy рабочим только по `systemctl active` или одному Wi-Fi подключению. Сначала
создайте отдельного тестового клиента, импортируйте URI и зафиксируйте version приложения/core.

## Матрица

Повторите полный checklist для каждой строки:

| Устройство | Сеть | Результат |
|---|---|---|
| Windows | Wi-Fi | ☐ |
| Android | Wi-Fi | ☐ |
| Android | LTE/5G | ☐ |
| iPhone | Wi-Fi | ☐ |
| iPhone | LTE/5G | ☐ |

## Checklist для каждой строки

1. Импортировать URI без ручного изменения полей.
2. Подключиться в VPN/TUN или supported proxy mode клиента.
3. Проверить внешний IPv4/IPv6 и записать ожидаемый/фактический результат.
4. Открыть несколько HTTPS endpoints; убедиться, что certificate warnings отсутствуют.
5. Проверить несколько независимых зарубежных сайтов.
6. Проверить нужные приложения, а не только browser.
7. Проверить DNS resolver/leak тестом и записать результат (V0.1 ещё не делает split DNS).
8. Держать трафик минимум 5 минут.
9. Повторить минимум 15 минут с периодическими запросами/видео.
10. Disconnect/reconnect дважды.
11. При наличии mobile устройства выполнить Wi-Fi → mobile без переимпорта URI.
12. Выполнить mobile → Wi-Fi.

Для проверки внешнего IP используйте два независимых HTTPS-сервиса или известный корпоративный
endpoint. Не публикуйте URI на screenshots.

## Server-side evidence

```bash
sudo aza-vpn status
sudo aza-vpn config validate
systemctl status aza-xray.service --no-pager
journalctl -u aza-xray.service --since "10 minutes ago" --no-pager
ss -lntp | grep ':<PORT>'
```

Не проверяйте только `localhost`: важен путь конкретной access network до public VPS port.

## Если Wi-Fi работает, а LTE/5G нет

Не объявляйте причиной DPI без данных. Сравните по порядку:

1. **TCP connectivity:** доступен ли configured IPv4:port из mobile network; нет ли carrier или
   cloud firewall rule. Проверяйте разрешённым клиентским инструментом, не port scan.
2. **DNS:** если address — hostname, совпадает ли A/AAAA; работает ли direct IPv4 при временном
   диагностическом профиле.
3. **IPv4/IPv6:** какой address family выбрал клиент; нет ли broken AAAA, NAT64 или IPv6-only
   особенностей. V0.1 URI обычно использует переданный public IPv4.
4. **MTU/PMTU:** признаки — connect успешен, small requests проходят, крупные зависают. Сравните
   меньший client TUN MTU, не меняя server firewall глобально.
5. **Packet loss/jitter:** повторите в разных местах/времени, запишите latency/loss.
6. **Timeout/reset:** отличайте timeout, immediate reset и TLS/Reality rejection по client log.
7. **Reality handshake:** сверьте UUID, SNI, `pbk`, `sid`, fingerprint и Vision flow; проверьте
   время устройства.
8. **Client logs:** сохраните минимальный фрагмент с timestamp, core/app version и типом сети.
9. **Server logs:** сопоставьте тот же timestamp через journal. Отсутствие события отличается от
   authentication failure.

Дополнительно сравните другой mobile carrier/device тем же тестовым URI. Меняйте за раз только
один параметр, иначе причина останется неизвестной.

## Критерий V0.1

V0.1 можно считать подтверждённой на VPS только после successful matrix либо после явно
зафиксированных исключений с диагностикой. Это не подтверждает будущий RU split-routing/split DNS.

