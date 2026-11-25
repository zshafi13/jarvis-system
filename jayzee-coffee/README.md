# JayZee Coffee Co ☕

Home coffee ordering app. Family members order from their phones; the barista
(you) sees every order on a separate screen and marks them done.

## Run it

Needs only Python 3 (no installs).

```bash
cd jayzee-coffee
python3 server.py          # or: python3 server.py --port 9000
```

It prints two links using the computer's local IP, e.g.:

| Who        | Open                              |
|------------|-----------------------------------|
| Family     | `http://192.168.1.50:8080/`       |
| Barista    | `http://192.168.1.50:8080/barista` |

Everyone must be on the same Wi-Fi. Tip: on phones, use "Add to Home Screen".

## How it works

- **Order page**: pick a season favorite or build a drink (drink, flavor, hot/iced),
  enter a name (remembered on that phone) and optional notes. The "My Orders"
  section shows *Brewing…* until you mark it done, then flips to *Ready ✓*
  (with a pop-up and vibration where supported).
- **Barista page**: oldest orders first, big **Done ✓** buttons, Cancel,
  Undo from the Finished list, and "Clear finished". Turn on 🔔 Sound for a
  chime when a new order comes in. Updates every few seconds.
- Orders are saved to `orders.json` next to `server.py`, so they survive a restart.

If other devices can't connect, allow Python through the computer's firewall
for private networks.
